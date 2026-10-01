"""Board and move encoding shared by data extraction, training and inference.

Perspective: every position is seen from the side to move. When Black is to
move the board is mirrored (``chess.Board.mirror``: ranks flipped, colors
swapped), so the network always plays "White, moving up the board".

Compact record (``COMPACT_BYTES`` = 67 bytes per position, uint8):

- bytes 0..63: piece code per square in the mirrored frame (a1 = 0 .. h8 = 63):
  0 empty, 1..6 own P N B R Q K, 7..12 opponent P N B R Q K;
- byte 64: castling bits (1 own O-O, 2 own O-O-O, 4 opponent O-O, 8 opponent O-O-O);
- byte 65: en-passant file + 1 (0 = none), in the mirrored frame;
- byte 66: half-move clock, clipped to 255.

Input planes (``PLANES`` = 19, each 8x8, row = rank, column = file):
12 piece planes (own P..K, opponent P..K), 4 castling planes (all ones or all
zeros), 1 en-passant plane (the capture target square), 1 half-move-clock
plane (clock / 100), 1 constant plane of ones.

Policy index: ``from_square * 64 + to_square`` in the mirrored frame (4096
logits). A promotion to a queen uses its plain from/to index. Under-promotions
have no index: the network can never play one, and training positions whose
played move is an under-promotion are dropped (they are rare, and this is a
documented limitation, see docs/ARCHITECTURE.md).
"""

from __future__ import annotations

import chess
import numpy as np

COMPACT_BYTES = 67
PLANES = 19
POLICY_SIZE = 4096


def _frame(board: chess.Board) -> chess.Board:
    return board if board.turn == chess.WHITE else board.mirror()


def compact(board: chess.Board) -> np.ndarray:
    """The 67-byte compact record of ``board`` from the side to move."""
    b = _frame(board)
    out = np.zeros(COMPACT_BYTES, dtype=np.uint8)
    for sq, piece in b.piece_map().items():
        out[sq] = piece.piece_type + (0 if piece.color == chess.WHITE else 6)
    flags = 0
    if b.has_kingside_castling_rights(chess.WHITE):
        flags |= 1
    if b.has_queenside_castling_rights(chess.WHITE):
        flags |= 2
    if b.has_kingside_castling_rights(chess.BLACK):
        flags |= 4
    if b.has_queenside_castling_rights(chess.BLACK):
        flags |= 8
    out[64] = flags
    ep = b.ep_square if b.has_legal_en_passant() else None
    out[65] = 0 if ep is None else chess.square_file(ep) + 1
    out[66] = min(b.halfmove_clock, 255)
    return out


def planes_np(rec: np.ndarray) -> np.ndarray:
    """(N, 67) uint8 compact records to (N, 19, 8, 8) float32 planes (CPU inference)."""
    rec = np.atleast_2d(rec)
    n = rec.shape[0]
    x = np.zeros((n, PLANES, 64), dtype=np.float32)
    sq = rec[:, :64].astype(np.int64)
    rows, cols = np.nonzero(sq)
    x[rows, sq[rows, cols] - 1, cols] = 1.0
    flags = rec[:, 64]
    for bit in range(4):
        x[:, 12 + bit, :] = ((flags >> bit) & 1)[:, None]
    ep = rec[:, 65].astype(np.int64)
    has = np.nonzero(ep)[0]
    # Opponent just double-pushed; the capture target is on rank 6 of our frame.
    x[has, 16, 40 + ep[has] - 1] = 1.0
    x[:, 17, :] = (rec[:, 66].astype(np.float32) / 100.0)[:, None]
    x[:, 18, :] = 1.0
    return x.reshape(n, PLANES, 8, 8)


def move_index(board: chess.Board, move: chess.Move) -> int | None:
    """Policy index of ``move`` in ``board``'s side-to-move frame; None for an under-promotion."""
    if move.promotion is not None and move.promotion != chess.QUEEN:
        return None
    f, t = move.from_square, move.to_square
    if board.turn == chess.BLACK:
        f, t = chess.square_mirror(f), chess.square_mirror(t)
    return f * 64 + t


def legal_indices(board: chess.Board) -> tuple[list[chess.Move], np.ndarray]:
    """Legal moves that have a policy index, with their indices."""
    moves, idx = [], []
    for m in board.legal_moves:
        i = move_index(board, m)
        if i is not None:
            moves.append(m)
            idx.append(i)
    return moves, np.asarray(idx, dtype=np.int64)
