// The real exported model through onnxruntime-web's WebAssembly backend in Node,
// against the Python onnxruntime results recorded in receipts/web-v1/parity.json.
// Skipped when the export directory is absent (model files are never in git):
// set CHESS_LAB_EXPORT or run scripts/export_web.py first.
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { Chess } from "chess.js";
import * as ort from "onnxruntime-web";
import { describe, expect, it } from "vitest";
import { compact, legalIndexed, pickMove, planes } from "../src/encode.js";

const EXPORT = process.env.CHESS_LAB_EXPORT ?? "D:/chess-lab-data/export";
const RECEIPT = new URL("../../receipts/web-v1/parity.json", import.meta.url);
const ATOL = 1e-3;

interface Parity {
  readonly shipped: { file: string };
  readonly reexport: { sha256: string };
  readonly per_position: readonly { name: string; fen: string; top1: string; logit: number; margin: number | null }[];
}

const have = existsSync(join(EXPORT, "manifest.json")) && existsSync(RECEIPT);

describe.skipIf(!have)("exported model in onnxruntime-web (Node, wasm backend)", () => {
  it("plays the same top-1 move as Python onnxruntime on every parity position, logits within 1e-3", async () => {
    const parity = JSON.parse(readFileSync(RECEIPT, "utf8")) as Parity;
    const bytes = readFileSync(join(EXPORT, parity.shipped.file));
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(parity.reexport.sha256);
    ort.env.wasm.numThreads = 1;
    const session = await ort.InferenceSession.create(new Uint8Array(bytes), { executionProviders: ["wasm"] });
    let maxDiff = 0;
    let checked = 0;
    for (const p of parity.per_position) {
      const chess = new Chess(p.fen);
      const out = await session.run({ planes: new ort.Tensor("float32", planes(compact(chess)), [1, 19, 8, 8]) });
      const pick = pickMove(legalIndexed(chess), out.policy?.data as Float32Array);
      maxDiff = Math.max(maxDiff, Math.abs(pick.logit - p.logit));
      if (p.margin === null || p.margin > 2 * ATOL) {
        checked++;
        expect(pick.best.uci, p.name).toBe(p.top1);
      }
    }
    console.log(`onnxruntime-web (Node) vs Python onnxruntime: ${checked}/${parity.per_position.length} top-1 checked, max |top-1 logit diff| ${maxDiff}`);
    expect(maxDiff).toBeLessThanOrEqual(ATOL);
  });
});
