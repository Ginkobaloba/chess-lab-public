import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { Chess } from "chess.js";
import { describe, expect, it } from "vitest";
import { COMPACT_BYTES, PLANES, compact, legalIndexed, moveIndex, pickMove, planes, playUci } from "../src/encode.js";

interface GoldenCase {
  readonly name: string;
  readonly fen: string;
  readonly moves: string | null;
  readonly compact_hex: string;
  readonly planes_sha256: string;
  readonly legal: string;
}

const golden = JSON.parse(readFileSync(new URL("../../receipts/web-v1/encode_golden.json", import.meta.url), "utf8")) as {
  encoding: string;
  cases: GoldenCase[];
};

const hex = (b: Uint8Array): string => Buffer.from(b).toString("hex");
const sha = (x: Float32Array): string => createHash("sha256").update(new Uint8Array(x.buffer, x.byteOffset, x.byteLength)).digest("hex");
const legalText = (c: Chess): string => legalIndexed(c).map((m) => `${m.uci}:${m.index}`).join(" ");

describe("encoder golden (chesslab/encode.py via receipts/web-v1/encode_golden.json)", () => {
  it("covers the edge cases and seeded positions", () => {
    expect(golden.encoding).toBe("chess-lab/encode/v1");
    expect(golden.cases.length).toBe(64);
  });

  for (const c of golden.cases) {
    it(`${c.name}: FEN gives the same record, planes hash and legal indices`, () => {
      const board = new Chess(c.fen);
      expect(hex(compact(board))).toBe(c.compact_hex);
      expect(sha(planes(compact(board)))).toBe(c.planes_sha256);
      expect(legalText(board)).toBe(c.legal);
    });
    if (c.moves !== null) {
      it(`${c.name}: replaying the UCI moves from the start gives the same record`, () => {
        const board = new Chess();
        for (const u of (c.moves as string).split(" ")) playUci(board, u);
        expect(hex(compact(board))).toBe(c.compact_hex);
        expect(legalText(board)).toBe(c.legal);
      });
    }
  }
});

describe("encoder details", () => {
  it("batches compact records into n x 19 x 8 x 8 planes", () => {
    const a = compact(new Chess());
    const b = compact(new Chess("r3k2r/8/8/8/8/8/8/R3K2R b Kq - 12 30"));
    const both = new Uint8Array(2 * COMPACT_BYTES);
    both.set(a, 0);
    both.set(b, COMPACT_BYTES);
    const x = planes(both);
    expect(x.length).toBe(2 * PLANES * 64);
    expect(sha(x.slice(0, PLANES * 64))).toBe(sha(planes(a)));
    expect(sha(x.slice(PLANES * 64))).toBe(sha(planes(b)));
  });

  it("indexes Black's moves in the mirrored frame", () => {
    // e7e5 for Black is e2e4 in the side-to-move frame.
    expect(moveIndex("b", { from: "e7", to: "e5" })).toBe(moveIndex("w", { from: "e2", to: "e4" }));
    expect(moveIndex("w", { from: "b7", to: "b8", promotion: "n" })).toBeNull();
  });

  it("refuses malformed and illegal UCI text", () => {
    expect(() => playUci(new Chess(), "e2e5")).toThrow(/illegal move/);
    expect(() => playUci(new Chess(), "e2-e4")).toThrow(/not a UCI move/);
  });

  it("picks the legal arg-max, never an illegal index", () => {
    const board = new Chess();
    const legal = legalIndexed(board);
    const logits = new Float32Array(4096).fill(-10);
    logits[0] = 100; // a1a1: not a legal move
    const e2e4 = legal.find((m) => m.uci === "e2e4");
    logits[e2e4?.index as number] = 5;
    const pick = pickMove(legal, logits);
    expect(pick.best.uci).toBe("e2e4");
    expect(pick.margin).toBe(15);
    expect(() => pickMove([], logits)).toThrow(/no legal moves/);
  });
});
