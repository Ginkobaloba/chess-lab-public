"""Reference positions and the encoder golden for the browser build (web/).

The browser re-implements ``chesslab/encode.py`` in TypeScript
(``web/src/encode.ts``) on top of chess.js. The contract between the two is
``receipts/web-v1/encode_golden.json``: for a fixed, seeded set of positions it
records the 67-byte compact record, the SHA-256 of the float32 input planes
(little-endian, NCHW, shape 1 x 19 x 8 x 8) and every legal move with its
policy index. ``web/test/encode.test.ts`` must reproduce all of it, and
``tests/test_web_golden.py`` regenerates the file and compares bytes, so
neither side can drift silently.

The golden is output of this program (python-chess computes the legal moves);
it contains no python-chess code, so nothing GPL enters the browser bundle
(docs/LICENSES.md).
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import chess
import numpy as np

from chesslab import encode
from chesslab.seeds import derive_seed

ENCODING = "chess-lab/encode/v1"
POSITION_SEED_BASE = "chess-lab-web-positions-v1"
OPENINGS = Path(__file__).resolve().parent / "data" / "openings.json"

# Hand-picked positions for the cases random play rarely reaches. Each one is
# a FEN that both python-chess and chess.js 1.4.0 accept.
EDGE_FENS: list[tuple[str, str]] = [
    ("start", chess.STARTING_FEN),
    ("ep legal for White", "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3"),
    ("ep legal for Black", "rnbqkbnr/pppp1ppp/8/8/3PpP2/8/PPP1P1PP/RNBQKBNR b KQkq f3 0 3"),
    ("ep square set, no pawn can capture", "rnbqkbnr/pppp1ppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"),
    ("ep capture pseudo-legal but pinned along the rank", "7k/8/8/KPp4r/8/8/8/8 w - c6 0 2"),
    ("castling rights mixed, Black to move", "r3k2r/8/8/8/8/8/8/R3K2R b Kq - 12 30"),
    ("all castling available", "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1"),
    ("castling through check refused", "r3k2r/8/8/8/8/8/5r2/R3K2R w KQkq - 0 1"),
    ("White promotion (queen indexed, under-promotions dropped)", "8/1P6/8/8/8/8/6k1/K7 w - - 0 1"),
    ("Black promotion with captures", "k7/8/8/8/8/8/1p4K1/R1N5 b - - 0 1"),
    ("half-move clock 99", "8/8/4k3/8/8/4K3/4P3/8 w - - 99 120"),
    ("half-move clock 150, Black to move", "8/8/4k3/8/8/4K3/4P3/8 b - - 150 120"),
    ("half-move clock 300 (clipped to 255)", "8/8/4k3/8/8/4K3/4P3/8 w - - 300 200"),
    ("in check, few legal moves", "4k3/8/8/8/8/8/3q4/4K3 w - - 0 1"),
    ("checkmated (no legal moves)", "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"),
    ("stalemate (no legal moves)", "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"),
]


def seeded_positions(n: int, max_random_plies: int = 60) -> list[tuple[str, list[str]]]:
    """``n`` positions as (fen, uci moves from the start position).

    Position i starts from opening ``i % 100`` of the ladder book
    (chesslab/data/openings.json) and adds up to ``max_random_plies`` uniformly
    random legal moves drawn from ``random.Random(derive_seed(POSITION_SEED_BASE, i))``
    (moves sorted by UCI text before the draw). It stops early at a game end.
    """
    book = json.loads(OPENINGS.read_text(encoding="utf-8"))["openings"]
    out: list[tuple[str, list[str]]] = []
    for i in range(n):
        rng = random.Random(derive_seed(POSITION_SEED_BASE, i))
        board = chess.Board()
        moves = list(book[i % len(book)])
        for u in moves:
            board.push_uci(u)
        for _ in range(rng.randrange(max_random_plies + 1)):
            legal = sorted(board.legal_moves, key=lambda m: m.uci())
            if not legal:
                break
            m = rng.choice(legal)
            board.push(m)
            moves.append(m.uci())
        out.append((board.fen(), moves))
    return out


def planes_sha256(board: chess.Board) -> str:
    x = encode.planes_np(encode.compact(board)).astype("<f4", copy=False)
    return hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest()


def position_record(board: chess.Board) -> dict[str, object]:
    moves, idx = encode.legal_indices(board)
    legal = sorted(zip((m.uci() for m in moves), idx.tolist()), key=lambda t: t[1])
    return {
        "compact_hex": encode.compact(board).tobytes().hex(),
        "planes_sha256": planes_sha256(board),
        # "uci:index" pairs sorted by index, space separated (keeps the file small).
        "legal": " ".join(f"{u}:{i}" for u, i in legal),
    }


def build_golden(n_seeded: int = 48) -> dict[str, object]:
    cases: list[dict[str, object]] = []
    for name, fen in EDGE_FENS:
        cases.append({"name": name, "fen": fen, "moves": None, **position_record(chess.Board(fen))})
    for i, (fen, moves) in enumerate(seeded_positions(n_seeded)):
        cases.append({"name": f"seeded {i}", "fen": fen, "moves": " ".join(moves), **position_record(chess.Board(fen))})
    return {
        "schema": "chess-lab/encode-golden/v1",
        "encoding": ENCODING,
        "generator": "chesslab/webref.py build_golden",
        "position_seed_base": POSITION_SEED_BASE,
        "planes": "float32 little-endian, NCHW 1 x 19 x 8 x 8, layout in chesslab/encode.py",
        "policy_index": "from * 64 + to in the side-to-move frame, a1 = 0; queen promotions only",
        "cases": cases,
    }


def golden_text(golden: dict[str, object]) -> str:
    return json.dumps(golden, indent=1) + "\n"
