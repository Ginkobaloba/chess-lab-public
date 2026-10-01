/**
 * Board and move encoding, a port of chesslab/encode.py on top of chess.js.
 *
 * The contract is receipts/web-v1/encode_golden.json (written by
 * scripts/gen_encode_golden.py from the Python encoder): the same 67-byte
 * compact record, the same float32 input planes (checked by SHA-256) and the
 * same legal-move policy indices for every case. test/encode.test.ts checks it.
 *
 * Frame: the side to move always plays "White, moving up the board". When
 * Black is to move the board is mirrored (ranks flipped: square s becomes
 * s ^ 56, colors swapped), as python-chess `Board.mirror()` does.
 *
 * Squares are numbered a1 = 0 .. h8 = 63 (python-chess order).
 */
import type { Chess, Move, Square } from "chess.js";

export const COMPACT_BYTES = 67;
export const PLANES = 19;
export const POLICY_SIZE = 4096;
export const ENCODING = "chess-lab/encode/v1";

const PIECE_CODE: Readonly<Record<string, number>> = { p: 1, n: 2, b: 3, r: 4, q: 5, k: 6 };

/** a1 = 0 .. h8 = 63. */
export function squareIndex(sq: string): number {
  const file = sq.charCodeAt(0) - 97;
  const rank = sq.charCodeAt(1) - 49;
  if (sq.length !== 2 || file < 0 || file > 7 || rank < 0 || rank > 7) throw new Error(`bad square ${JSON.stringify(sq)}`);
  return rank * 8 + file;
}

/** Castling rights as python-chess `clean_castling_rights` sees them in standard chess. */
function castling(chess: Chess, color: "w" | "b"): { k: boolean; q: boolean } {
  const rank = color === "w" ? "1" : "8";
  const at = (file: string, type: string): boolean => {
    const p = chess.get(`${file}${rank}` as Square);
    return p !== undefined && p !== null && p.color === color && p.type === type;
  };
  const rights = chess.getCastlingRights(color);
  const king = at("e", "k");
  return { k: king && rights.k === true && at("h", "r"), q: king && rights.q === true && at("a", "r") };
}

/** The 67-byte compact record of the position, from the side to move (chesslab/encode.py `compact`). */
export function compact(chess: Chess): Uint8Array {
  const out = new Uint8Array(COMPACT_BYTES);
  const us = chess.turn();
  const them = us === "w" ? "b" : "w";
  const flip = us === "b" ? 56 : 0;
  for (const row of chess.board()) {
    for (const cell of row) {
      if (cell === null) continue;
      const code = (PIECE_CODE[cell.type] as number) + (cell.color === us ? 0 : 6);
      out[squareIndex(cell.square) ^ flip] = code;
    }
  }
  const own = castling(chess, us);
  const opp = castling(chess, them);
  out[64] = (own.k ? 1 : 0) | (own.q ? 2 : 0) | (opp.k ? 4 : 0) | (opp.q ? 8 : 0);
  // python-chess sets the en-passant byte only when an en-passant capture is legal
  // (`has_legal_en_passant`), so it comes from the legal moves, never from the FEN field.
  const ep = chess.moves({ verbose: true }).find((m) => m.isEnPassant());
  out[65] = ep === undefined ? 0 : ep.to.charCodeAt(0) - 97 + 1;
  const clock = Number(chess.fen().split(" ")[4] ?? "0");
  out[66] = Math.min(Number.isFinite(clock) ? clock : 0, 255);
  return out;
}

/** Compact records (concatenated, n x 67) to float32 planes, n x 19 x 8 x 8 (chesslab/encode.py `planes_np`). */
export function planes(rec: Uint8Array): Float32Array {
  if (rec.length % COMPACT_BYTES !== 0) throw new Error(`planes: ${rec.length} bytes is not a multiple of ${COMPACT_BYTES}`);
  const n = rec.length / COMPACT_BYTES;
  const x = new Float32Array(n * PLANES * 64);
  for (let i = 0; i < n; i++) {
    const r = rec.subarray(i * COMPACT_BYTES, (i + 1) * COMPACT_BYTES);
    const base = i * PLANES * 64;
    for (let sq = 0; sq < 64; sq++) {
      const code = r[sq] as number;
      if (code !== 0) x[base + (code - 1) * 64 + sq] = 1;
    }
    const flags = r[64] as number;
    for (let bit = 0; bit < 4; bit++) {
      if ((flags >> bit) & 1) x.fill(1, base + (12 + bit) * 64, base + (13 + bit) * 64);
    }
    const ep = r[65] as number;
    // Opponent just double-pushed; the capture target is on rank 6 of our frame.
    if (ep > 0) x[base + 16 * 64 + 40 + ep - 1] = 1;
    // float32(clock) / 100 in numpy is one correctly rounded float32 division; rounding the
    // float64 quotient to float32 gives the same value (53 >= 2 * 24 + 2).
    x.fill(Math.fround((r[66] as number) / 100), base + 17 * 64, base + 18 * 64);
    x.fill(1, base + 18 * 64, base + 19 * 64);
  }
  return x;
}

/** Policy index of a chess.js move in the side-to-move frame; null for an under-promotion. */
export function moveIndex(turn: "w" | "b", move: Pick<Move, "from" | "to" | "promotion">): number | null {
  if (move.promotion !== undefined && move.promotion !== "q") return null;
  const flip = turn === "b" ? 56 : 0;
  return (squareIndex(move.from) ^ flip) * 64 + (squareIndex(move.to) ^ flip);
}

/** UCI text of a chess.js move (e2e4, e7e8q). */
export function uci(move: Pick<Move, "from" | "to" | "promotion">): string {
  return `${move.from}${move.to}${move.promotion ?? ""}`;
}

export interface IndexedMove {
  readonly uci: string;
  readonly san: string;
  readonly index: number;
}

/** Legal moves that have a policy index (under-promotions dropped), sorted by index. */
export function legalIndexed(chess: Chess): IndexedMove[] {
  const turn = chess.turn();
  const out: IndexedMove[] = [];
  for (const m of chess.moves({ verbose: true })) {
    const index = moveIndex(turn, m);
    if (index !== null) out.push({ uci: uci(m), san: m.san, index });
  }
  return out.sort((a, b) => a.index - b.index);
}

const UCI_RE = /^([a-h][1-8])([a-h][1-8])([qrbn])?$/;

/** Plays a UCI move; throws on malformed or illegal text. */
export function playUci(chess: Chess, text: string): Move {
  const m = UCI_RE.exec(text);
  if (m === null) throw new Error(`not a UCI move: ${JSON.stringify(text)}`);
  const [, from, to, promotion] = m;
  try {
    return chess.move({ from: from as string, to: to as string, promotion });
  } catch {
    throw new Error(`illegal move ${JSON.stringify(text)} in ${chess.fen()}`);
  }
}

/** Legal arg-max over the policy logits, plus the margin to the second-best legal move. */
export function pickMove(legal: readonly IndexedMove[], logits: Float32Array): { best: IndexedMove; logit: number; margin: number; top: { uci: string; logit: number }[] } {
  if (legal.length === 0) throw new Error("no legal moves (checkmate or stalemate)");
  // Exact ties go to the lower policy index. The Python player takes the first in
  // python-chess generation order instead; the parity receipt records each position's
  // top-two margin, and none of its positions is an exact tie.
  const ranked = legal.map((m) => ({ m, l: logits[m.index] as number })).sort((a, b) => b.l - a.l || a.m.index - b.m.index);
  const first = ranked[0] as { m: IndexedMove; l: number };
  const second = ranked[1];
  return {
    best: first.m,
    logit: first.l,
    margin: second === undefined ? Number.POSITIVE_INFINITY : first.l - second.l,
    top: ranked.slice(0, 5).map((r) => ({ uci: r.m.uci, logit: r.l })),
  };
}
