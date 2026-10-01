import { createHash, webcrypto } from "node:crypto";
import { describe, expect, it } from "vitest";
import { type CoreEnv, EngineCore, type Session } from "../src/core.js";
import { legalIndexed } from "../src/encode.js";
import type { EventMessage } from "../src/protocol.js";
import { PROTOCOL_VERSION } from "../src/protocol.js";
import { Chess } from "chess.js";

const MODEL = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]);
const SHA = createHash("sha256").update(MODEL).digest("hex");
const BASE = "https://lab.test/chess/model/";

function manifest(over: Record<string, unknown> = {}) {
  return {
    schema: "chess-lab/web-model/v1",
    encoding: "chess-lab/encode/v1",
    models: [{ id: "fp32", file: "m.onnx", bytes: MODEL.length, sha256: SHA, rated: true, step: 80000, ...over }],
  };
}

/** A session whose logits favour a fixed index order; `gate` holds a run open until released. */
class FakeSession implements Session {
  running = 0;
  maxConcurrent = 0;
  runs = 0;
  gate: Promise<void> | null = null;
  async run(_planes: Float32Array) {
    this.running++;
    this.runs++;
    this.maxConcurrent = Math.max(this.maxConcurrent, this.running);
    if (this.gate !== null) await this.gate;
    this.running--;
    const policy = new Float32Array(4096);
    for (let i = 0; i < 4096; i++) policy[i] = -i / 4096;
    policy[0] = 1000; // a1a1, never legal: masking must ignore it
    return { policy, wdl: new Float32Array([0, 0, 0]) };
  }
}

function setup(opts: { manifest?: unknown; model?: Uint8Array; subtle?: boolean } = {}) {
  const events: EventMessage[] = [];
  const session = new FakeSession();
  const fetched: string[] = [];
  const env: CoreEnv = {
    fetch: async (url) => {
      fetched.push(url);
      if (url === `${BASE}manifest.json`) {
        const m = opts.manifest ?? manifest();
        return { ok: true, status: 200, json: async () => m, arrayBuffer: async () => new ArrayBuffer(0) };
      }
      if (url === `${BASE}m.onnx`) {
        const b = (opts.model ?? MODEL).slice();
        return { ok: true, status: 200, json: async () => null, arrayBuffer: async () => b.buffer };
      }
      return { ok: false, status: 404, json: async () => null, arrayBuffer: async () => new ArrayBuffer(0) };
    },
    subtle: opts.subtle === false ? undefined : (webcrypto.subtle as unknown as SubtleCrypto),
    now: () => performance.now(),
    yieldNow: () => new Promise((r) => setImmediate(r)),
    createSession: async () => session,
    baseUrl: "https://lab.test/chess/worker.js",
  };
  const core = new EngineCore((m) => events.push(m as EventMessage), env);
  const send = (id: number, req: Record<string, unknown>) => core.handle({ ...req, v: PROTOCOL_VERSION, id });
  const terminal = async (id: number): Promise<EventMessage> => {
    for (let i = 0; i < 1000; i++) {
      const e = events.find((x) => x.id === id && x.type !== "ready");
      if (e !== undefined) return e;
      await new Promise((r) => setImmediate(r));
    }
    throw new Error(`no event for request ${id}`);
  };
  return { core, events, session, send, terminal, fetched };
}

async function loaded() {
  const t = setup();
  await t.send(1, { type: "load", manifestUrl: "model/manifest.json", model: "fp32" });
  expect((await t.terminal(1)).type).toBe("loaded");
  return t;
}

describe("protocol envelope", () => {
  it("announces itself and refuses other protocol versions and unknown types", async () => {
    const t = setup();
    t.core.ready();
    expect(t.events[0]).toEqual({ type: "ready", protocol: 1, v: 1, id: 0 });
    await t.core.handle({ type: "bestMove", v: 2, id: 5 });
    expect(await t.terminal(5)).toMatchObject({ type: "error", message: expect.stringMatching(/protocol 1/) });
    await t.send(6, { type: "train" });
    expect(await t.terminal(6)).toMatchObject({ type: "error", message: expect.stringMatching(/unknown request type/) });
  });

  it("refuses bestMove before a model is loaded", async () => {
    const t = setup();
    await t.send(2, { type: "bestMove" });
    expect(await t.terminal(2)).toMatchObject({ type: "error", message: expect.stringMatching(/no model loaded/) });
  });
});

describe("load", () => {
  it("resolves the manifest against the worker URL, checks bytes and sha256, reports the model", async () => {
    const t = await loaded();
    expect(t.fetched).toEqual([`${BASE}manifest.json`, `${BASE}m.onnx`]);
    const e = t.events.find((x) => x.id === 1);
    expect(e).toMatchObject({ type: "loaded", model: { id: "fp32", bytes: 8, sha256: SHA, rated: true, step: 80000 } });
  });

  const bad: [string, Parameters<typeof setup>[0], RegExp][] = [
    ["a sha256 mismatch", { model: new Uint8Array([1, 2, 3, 4, 5, 6, 7, 9]) }, /does not match/],
    ["a byte-count mismatch", { model: new Uint8Array([1, 2, 3]) }, /3 bytes, manifest says 8/],
    ["a file outside the manifest directory", { manifest: manifest({ file: "../m.onnx" }) }, /outside the manifest's directory/],
    ["another origin", { manifest: manifest({ file: "https://evil.test/m.onnx" }) }, /outside the manifest's directory/],
    ["a different encoding", { manifest: { ...manifest(), encoding: "chess-lab/encode/v2" } }, /encoding/],
    ["no crypto.subtle", { subtle: false }, /crypto.subtle is unavailable/],
  ];
  for (const [what, opts, re] of bad) {
    it(`refuses ${what}`, async () => {
      const t = setup(opts);
      await t.send(1, { type: "load", manifestUrl: "model/manifest.json", model: "fp32" });
      expect(await t.terminal(1)).toMatchObject({ type: "error", message: expect.stringMatching(re) });
      expect(t.core.loadedModel).toBeNull();
    });
  }
});

describe("bestMove", () => {
  it("plays the legal arg-max, never the illegal top logit", async () => {
    const t = await loaded();
    await t.send(2, { type: "bestMove" });
    const e = await t.terminal(2);
    const legal = legalIndexed(new Chess());
    const lowest = legal.reduce((a, b) => (a.index < b.index ? a : b));
    expect(e).toMatchObject({ type: "bestMove", move: lowest.uci, index: lowest.index, legalCount: 20 });
    expect((e as unknown as { wdl: number[] }).wdl.map((p) => Math.round(p * 1000))).toEqual([333, 333, 333]);
  });

  it("replays UCI moves from a FEN and from the start position", async () => {
    const t = await loaded();
    await t.send(2, { type: "bestMove", moves: ["e2e4", "e7e5", "g1f3"] });
    expect(await t.terminal(2)).toMatchObject({ type: "bestMove", fen: "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2" });
    await t.send(3, { type: "bestMove", fen: "8/1P6/8/8/8/8/6k1/K7 w - - 0 1", moves: [] });
    // 4 promotions exist, only the queen one has an index: b7b8q plus the king's 3 moves.
    expect(await t.terminal(3)).toMatchObject({ type: "bestMove", legalCount: 4 });
  });

  const bad: [string, Record<string, unknown>, RegExp][] = [
    ["an invalid FEN", { fen: "not a fen" }, /invalid FEN/],
    ["an illegal move", { moves: ["e2e5"] }, /illegal move "e2e5"/],
    ["malformed move text", { moves: ["Nf3"] }, /not a UCI move/],
    ["moves that are not strings", { moves: [1] }, /array of strings/],
    ["a checkmated side", { fen: "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3" }, /no legal moves/],
  ];
  for (const [what, req, re] of bad) {
    it(`refuses ${what}`, async () => {
      const t = await loaded();
      await t.send(2, { type: "bestMove", ...req });
      expect(await t.terminal(2)).toMatchObject({ type: "error", message: expect.stringMatching(re) });
    });
  }

  it("evaluates one request at a time, in arrival order", async () => {
    const t = await loaded();
    for (let id = 10; id < 15; id++) void t.send(id, { type: "bestMove" });
    for (let id = 10; id < 15; id++) expect((await t.terminal(id)).type).toBe("bestMove");
    const order = t.events.filter((e) => e.type === "bestMove").map((e) => e.id);
    expect(order).toEqual([10, 11, 12, 13, 14]);
    expect(t.session.maxConcurrent).toBe(1);
  });
});

describe("cancel", () => {
  it("drops a queued request by id and leaves the others alone", async () => {
    const t = await loaded();
    void t.send(10, { type: "bestMove" });
    void t.send(11, { type: "bestMove" });
    void t.send(12, { type: "bestMove" });
    void t.send(13, { type: "cancel", target: 11 });
    expect((await t.terminal(11)).type).toBe("cancelled");
    expect((await t.terminal(10)).type).toBe("bestMove");
    expect((await t.terminal(12)).type).toBe("bestMove");
    expect(t.session.runs).toBe(2);
    expect(t.events.some((e) => e.id === 13)).toBe(false); // cancel has no reply of its own
  });

  it("wins against a request posted just before it (the request yields before it evaluates)", async () => {
    const t = await loaded();
    void t.send(20, { type: "bestMove" });
    void t.send(21, { type: "cancel", target: 20 });
    expect((await t.terminal(20)).type).toBe("cancelled");
    expect(t.session.runs).toBe(0);
  });

  it("discards an in-flight evaluation and reports cancelled", async () => {
    const t = await loaded();
    let release = () => undefined as void;
    t.session.gate = new Promise<void>((r) => {
      release = r;
    });
    void t.send(30, { type: "bestMove" });
    while (t.session.running === 0) await new Promise((r) => setImmediate(r));
    void t.send(31, { type: "cancel", target: 30 });
    release();
    expect((await t.terminal(30)).type).toBe("cancelled");
    expect(t.events.filter((e) => e.id === 30).length).toBe(1);
  });

  it("without a target cancels everything; with an unknown target does nothing", async () => {
    const t = await loaded();
    void t.send(40, { type: "bestMove" });
    void t.send(41, { type: "bestMove" });
    void t.send(42, { type: "cancel", target: 999 });
    void t.send(43, { type: "cancel" });
    expect((await t.terminal(40)).type).toBe("cancelled");
    expect((await t.terminal(41)).type).toBe("cancelled");
    await t.send(44, { type: "cancel", target: 1.5 });
    expect(await t.terminal(44)).toMatchObject({ type: "error", message: expect.stringMatching(/target must be a request id/) });
  });
});
