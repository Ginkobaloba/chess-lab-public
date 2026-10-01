import chess
import numpy as np
import torch

from chesslab import encode
from chesslab.model import Net, planes_torch

FENS = [
    chess.STARTING_FEN,
    "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3",  # legal en passant for White
    "rnbqkbnr/pppp1ppp/8/8/3PpP2/8/PPP1P1PP/RNBQKBNR b KQkq f3 0 3",  # legal en passant for Black
    "r3k2r/8/8/8/8/8/8/R3K2R b Kq - 12 30",
    "8/1P6/8/8/8/8/6k1/K7 w - - 0 1",
]


def test_planes_numpy_matches_torch():
    recs = np.stack([encode.compact(chess.Board(f)) for f in FENS])
    a = encode.planes_np(recs)
    b = planes_torch(torch.from_numpy(recs)).numpy()
    assert a.shape == (len(FENS), encode.PLANES, 8, 8)
    np.testing.assert_array_equal(a, b)


def test_black_to_move_is_mirrored():
    white = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    black = white.mirror()
    black.turn = chess.BLACK
    np.testing.assert_array_equal(encode.compact(white), encode.compact(black))


def test_en_passant_plane():
    rec = encode.compact(chess.Board(FENS[2]))
    assert rec[65] == chess.square_file(chess.F3) + 1
    x = encode.planes_np(rec)[0]
    # Mirrored frame: the capture target f3 becomes f6 = square 45 = row 5, col 5.
    assert x[16, 5, 5] == 1.0 and x[16].sum() == 1.0


def test_move_index_roundtrip_and_underpromotion():
    b = chess.Board(FENS[4])
    moves, idx = encode.legal_indices(b)
    assert len(set(idx.tolist())) == len(idx)
    assert encode.move_index(b, chess.Move.from_uci("b7b8n")) is None
    assert encode.move_index(b, chess.Move.from_uci("b7b8q")) == chess.B7 * 64 + chess.B8
    bb = chess.Board(FENS[3])
    m = chess.Move.from_uci("e8c8")
    assert encode.move_index(bb, m) == chess.E1 * 64 + chess.C1


def test_policy_layout():
    net = Net(blocks=1, channels=8).eval()
    x = torch.zeros(2, encode.PLANES, 8, 8)
    p, v = net(x)
    assert p.shape == (2, 4096) and v.shape == (2, 3)
    raw = net.pol(net.trunk(net.stem(x)))
    f, t = chess.E2, chess.E4
    assert torch.allclose(p[0, f * 64 + t], raw[0, t, f // 8, f % 8])
