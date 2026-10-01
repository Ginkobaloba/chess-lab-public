"""One arena game as a pure task (pattern from draughts-lab arena/game.py, rewritten for chess).

A game starts from a book opening (a list of UCI moves), then the two players
alternate. It ends on checkmate, stalemate, insufficient material, the
75-move or fivefold rule, a claimable threefold repetition or 50-move draw
(claimed automatically), or the ply cap (``MAX_PLIES``, scored as a draw and
recorded as ``cap``).
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass

import chess
import psutil

from chesslab.players import make_player

MAX_PLIES = 400


@dataclass(frozen=True)
class GameTask:
    game_id: str
    pairing: str
    a: str
    b: str
    a_spec: str
    b_spec: str
    a_is_white: bool
    seed: int
    opening_index: int
    opening: tuple[str, ...]


@dataclass
class GameRecord:
    game_id: str
    pairing: str
    a: str
    b: str
    a_is_white: bool
    seed: int
    opening_index: int
    score_a: float
    termination: str
    plies: int
    moves: str
    pid: int
    proc_started: float
    wall_s: float

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def _termination(board: chess.Board) -> tuple[str, chess.Color | None] | None:
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return None
    return outcome.termination.name.lower(), outcome.winner


def play(task: GameTask) -> GameRecord:
    t0 = time.monotonic()
    board = chess.Board()
    for uci in task.opening:
        board.push_uci(uci)
    white_spec, black_spec = (task.a_spec, task.b_spec) if task.a_is_white else (task.b_spec, task.a_spec)
    # Distinct, derived seeds per side so two seeded players never share a stream.
    white = make_player(white_spec, task.seed * 2 % (1 << 63))
    black = make_player(black_spec, (task.seed * 2 + 1) % (1 << 63))
    try:
        end = _termination(board)
        while end is None and board.ply() < MAX_PLIES:
            player = white if board.turn == chess.WHITE else black
            board.push(player.choose(board))
            end = _termination(board)
    finally:
        white.close()
        black.close()
    if end is None:
        term, winner = "cap", None
    else:
        term, winner = end
    if winner is None:
        score_a = 0.5
    else:
        a_color = chess.WHITE if task.a_is_white else chess.BLACK
        score_a = 1.0 if winner == a_color else 0.0
    proc = psutil.Process()
    return GameRecord(
        game_id=task.game_id,
        pairing=task.pairing,
        a=task.a,
        b=task.b,
        a_is_white=task.a_is_white,
        seed=task.seed,
        opening_index=task.opening_index,
        score_a=score_a,
        termination=term,
        plies=board.ply(),
        moves=" ".join(m.uci() for m in board.move_stack),
        pid=os.getpid(),
        proc_started=proc.create_time(),
        wall_s=round(time.monotonic() - t0, 3),
    )
