from pathlib import Path

import chess

from chesslab import encode, webref

GOLDEN = Path(__file__).resolve().parent.parent / "receipts" / "web-v1" / "encode_golden.json"


def test_encode_golden_is_current():
    # Regenerate in memory and compare bytes: a change to encode.py or the
    # position set must come with a regenerated golden (scripts/gen_encode_golden.py).
    assert GOLDEN.read_text(encoding="utf-8") == webref.golden_text(webref.build_golden())


def test_seeded_positions_are_deterministic():
    assert webref.seeded_positions(5) == webref.seeded_positions(5)


def test_edge_cases_cover_what_they_claim():
    names = dict(webref.EDGE_FENS)
    pinned = chess.Board(names["ep capture pseudo-legal but pinned along the rank"])
    assert pinned.ep_square is not None and not pinned.has_legal_en_passant()
    assert encode.compact(pinned)[65] == 0
    assert encode.compact(chess.Board(names["ep legal for White"]))[65] == chess.square_file(chess.F6) + 1
    assert encode.compact(chess.Board(names["half-move clock 300 (clipped to 255)"]))[66] == 255
    assert not any(chess.Board(names["stalemate (no legal moves)"]).legal_moves)
