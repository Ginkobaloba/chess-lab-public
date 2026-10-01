"""Ladder players, built from a spec string.

Specs:

- ``random``: a uniformly random legal move (seeded).
- ``material1``: 1-ply material greedy. Plays mate in one if available, else
  the move that maximizes (own material - opponent material) right after the
  move (P=1, N=B=3, R=5, Q=9); ties broken at random (seeded). It never looks
  at the reply, so it hangs pieces freely.
- ``material2``: 2-ply material minimax (our move, the opponent's best
  material reply), mate-aware, seeded ties.
- ``mix:<pct>:<spec a>|<spec b>``: each move, with probability pct/100 plays
  ``a``'s choice, else ``b``'s (seeded). A continuous strength knob used to
  fill gaps between rungs.
- ``sf:<k=v,...>``: Stockfish over UCI as an external binary (never linked).
  Keys: ``depth``, ``nodes``, ``movetime`` (ms) pick the search limit;
  ``skill`` sets ``Skill Level``; ``elo`` sets ``UCI_LimitStrength=true`` and
  ``UCI_Elo``. Always ``Threads=1``, ``Hash=16``.
- ``net:<path.onnx>``: an exported chess-lab network through onnxruntime on one
  CPU thread; plays the arg-max of the legal-move policy (one "node", as Maia
  does). Deterministic for a given position.

Determinism: ``random`` and ``material1`` are pure functions of their seed;
``sf`` with a depth or node limit and no skill/elo limit is deterministic on a
fresh process; ``sf`` with ``skill``/``elo`` is NOT (Stockfish seeds the weak-move
choice from time), and ``movetime`` limits are not either. The receipts are
the recorded games themselves, not a replay.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import chess
import chess.engine
import numpy as np

from chesslab import encode

STOCKFISH = Path(
    os.environ.get(
        "CHESS_LAB_STOCKFISH",
        "D:/chess-lab-data/bin/sf19/stockfish/stockfish-windows-x86-64-universal.exe",
    )
)

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


class Player:
    def choose(self, board: chess.Board) -> chess.Move:
        raise NotImplementedError

    def close(self) -> None:
        pass


class RandomPlayer(Player):
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def choose(self, board: chess.Board) -> chess.Move:
        return self.rng.choice(sorted(board.legal_moves, key=lambda m: m.uci()))


def material(board: chess.Board, color: chess.Color) -> int:
    total = 0
    for piece in board.piece_map().values():
        v = VALUES[piece.piece_type]
        total += v if piece.color == color else -v
    return total


class Material1Player(Player):
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def choose(self, board: chess.Board) -> chess.Move:
        me = board.turn
        best, best_moves = None, []
        for m in sorted(board.legal_moves, key=lambda m: m.uci()):
            board.push(m)
            score = 10_000 if board.is_checkmate() else material(board, me)
            board.pop()
            if best is None or score > best:
                best, best_moves = score, [m]
            elif score == best:
                best_moves.append(m)
        return self.rng.choice(best_moves)


def parse_kv(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for part in filter(None, text.split(",")):
        k, v = part.split("=")
        out[k.strip()] = int(v)
    return out


class StockfishPlayer(Player):
    def __init__(self, params: dict[str, int], binary: Path = STOCKFISH) -> None:
        # Generous init timeout: under full CPU load at BelowNormal priority, Stockfish's
        # startup (NNUE load) exceeded python-chess's 10 s default (ladder-v2, first attempt).
        self.engine = chess.engine.SimpleEngine.popen_uci(str(binary), timeout=120)
        opts: dict[str, object] = {"Threads": 1, "Hash": 16}
        if "elo" in params:
            opts["UCI_LimitStrength"] = True
            opts["UCI_Elo"] = params["elo"]
        if "skill" in params:
            opts["Skill Level"] = params["skill"]
        self.engine.configure(opts)
        if "depth" in params:
            self.limit = chess.engine.Limit(depth=params["depth"])
        elif "nodes" in params:
            self.limit = chess.engine.Limit(nodes=params["nodes"])
        elif "movetime" in params:
            self.limit = chess.engine.Limit(time=params["movetime"] / 1000.0)
        else:
            raise ValueError(f"sf spec needs depth, nodes or movetime: {params}")

    def choose(self, board: chess.Board) -> chess.Move:
        return self.engine.play(board, self.limit).move

    def close(self) -> None:
        try:
            self.engine.quit()
        except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError):
            pass


class NetPlayer(Player):
    def __init__(self, onnx_path: str) -> None:
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(onnx_path, so, providers=["CPUExecutionProvider"])

    def policy(self, board: chess.Board) -> tuple[list[chess.Move], np.ndarray]:
        x = encode.planes_np(encode.compact(board))
        logits = self.sess.run(["policy"], {"planes": x})[0][0]
        moves, idx = encode.legal_indices(board)
        return moves, logits[idx]

    def choose(self, board: chess.Board) -> chess.Move:
        moves, logits = self.policy(board)
        return moves[int(np.argmax(logits))]


class Material2Player(Player):
    """2-ply material minimax: maximize the material balance after the opponent's best material reply.

    Mate in one scores highest; a move that leaves the opponent no legal reply
    other than being mated is found at ply 1; stalemate after our move scores 0
    relative material (a draw). Ties broken at random (seeded).
    """

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def choose(self, board: chess.Board) -> chess.Move:
        me = board.turn
        best, best_moves = None, []
        for m in sorted(board.legal_moves, key=lambda m: m.uci()):
            board.push(m)
            if board.is_checkmate():
                score = 10_000
            elif board.is_stalemate() or board.is_insufficient_material():
                score = 0
            else:
                worst = None
                for r in board.legal_moves:
                    board.push(r)
                    s = -10_000 if board.is_checkmate() else material(board, me)
                    board.pop()
                    if worst is None or s < worst:
                        worst = s
                score = worst
            board.pop()
            if best is None or score > best:
                best, best_moves = score, [m]
            elif score == best:
                best_moves.append(m)
        return self.rng.choice(best_moves)


class MixPlayer(Player):
    """With probability ``pct``/100 play ``a``'s move, else ``b``'s (seeded coin; both players stay in sync)."""

    def __init__(self, pct: int, a: Player, b: Player, seed: int) -> None:
        self.pct, self.a, self.b = pct, a, b
        self.rng = random.Random(seed ^ 0x5EED)

    def choose(self, board: chess.Board) -> chess.Move:
        return (self.a if self.rng.random() * 100 < self.pct else self.b).choose(board)

    def close(self) -> None:
        self.a.close()
        self.b.close()


def make_player(spec: str, seed: int) -> Player:
    if spec == "random":
        return RandomPlayer(seed)
    if spec == "material1":
        return Material1Player(seed)
    if spec == "material2":
        return Material2Player(seed)
    if spec.startswith("mix:"):
        # mix:<pct>:<spec a>|<spec b>  -- e.g. mix:50:random|sf:depth=1
        _, pct, rest = spec.split(":", 2)
        a, b = rest.split("|", 1)
        return MixPlayer(int(pct), make_player(a, seed), make_player(b, seed + 1), seed)
    if spec.startswith("sf:"):
        return StockfishPlayer(parse_kv(spec[3:]))
    if spec.startswith("net:"):
        return NetPlayer(spec[4:])
    raise ValueError(f"unknown player spec {spec!r}")
