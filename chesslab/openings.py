"""The arena opening book: ``BOOK_SIZE`` distinct, roughly balanced 6-ply openings.

Why: most ladder players are deterministic (Stockfish at a fixed depth, the
network at arg-max), so games from the start position would repeat. Game ``i``
of a pairing plays opening ``(i // 2) % BOOK_SIZE`` with colors alternating, so
every opening is played from both sides and 200 games per pairing use 100
distinct openings exactly once per side.

Generation (``python -m chesslab.openings``), deterministic on a fixed
Stockfish binary: from the start position, each ply picks uniformly (seeded by
``derive_seed("openings", k, ply)``) among Stockfish MultiPV-5 depth-10 moves
within 50 cp of the best one; the 6-ply result is kept if a depth-14 eval is
within +/-60 cp and the position is new. The book and its generation facts are
written to ``chesslab/data/openings.json``.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import chess
import chess.engine

from chesslab.players import STOCKFISH
from chesslab.seeds import derive_seed

BOOK_SIZE = 100
PLIES = 6
BOOK_PATH = Path(__file__).resolve().parent / "data" / "openings.json"


def load_openings(path: Path = BOOK_PATH) -> list[list[str]]:
    return json.loads(path.read_text(encoding="utf-8"))["openings"]


def generate() -> dict[str, object]:
    eng = chess.engine.SimpleEngine.popen_uci(str(STOCKFISH))
    eng.configure({"Threads": 1, "Hash": 64})
    book: list[list[str]] = []
    evals: list[int] = []
    seen: set[str] = set()
    k = 0
    try:
        while len(book) < BOOK_SIZE:
            board = chess.Board()
            for ply in range(PLIES):
                infos = eng.analyse(board, chess.engine.Limit(depth=10), multipv=5)
                scored = [(i["score"].relative.score(mate_score=100_000), i["pv"][0]) for i in infos]
                best = max(s for s, _ in scored)
                cands = sorted((m for s, m in scored if s >= best - 50), key=lambda m: m.uci())
                board.push(random.Random(derive_seed("openings", k, ply)).choice(cands))
            k += 1
            fen = board.board_fen() + (" w" if board.turn else " b")
            if fen in seen:
                continue
            cp = eng.analyse(board, chess.engine.Limit(depth=14))["score"].white().score(mate_score=100_000)
            if abs(cp) > 60:
                continue
            seen.add(fen)
            book.append([m.uci() for m in board.move_stack])
            evals.append(cp)
        eng_name = eng.id.get("name", "unknown")
    finally:
        eng.quit()
    return {
        "generator": "chesslab/openings.py",
        "engine": eng_name,
        "attempts": k,
        "plies": PLIES,
        "white_cp_depth14": evals,
        "openings": book,
    }


if __name__ == "__main__":
    out = generate()
    BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOOK_PATH.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(out['openings'])} openings after {out['attempts']} attempts to {BOOK_PATH}")
