/**
 * Web Worker entry (dist/chess-lab-worker.js). All logic is in core.ts; this
 * file connects it to the worker global and to onnxruntime-web.
 *
 * onnxruntime-web runs single-threaded on its WebAssembly backend: threads
 * need SharedArrayBuffer, which needs cross-origin isolation (COOP and COEP
 * headers) that a host page cannot be assumed to send, and a one-position
 * evaluation of this net is small. The worker itself keeps it off the page's
 * main thread. The runtime fetches `ort-wasm-simd-threaded.wasm` from the
 * worker's own directory (pack.mjs copies it into dist/).
 *
 * Pattern follows Ginkobaloba/draughts-lab web/src/worker.ts at commit
 * 0a5c5a0fe6cc3443565937a738509f5de9479b19 (Paradigm-owned, MIT).
 */
import * as ort from "onnxruntime-web/wasm";
import { EngineCore, type Session } from "./core.js";

interface WorkerScope {
  postMessage(msg: unknown): void;
  onmessage: ((ev: MessageEvent) => void) | null;
  location: { href: string };
  crypto?: Crypto;
}

const scope = globalThis as unknown as WorkerScope;

ort.env.wasm.numThreads = 1;
ort.env.wasm.proxy = false;
ort.env.wasm.wasmPaths = { wasm: new URL("ort-wasm-simd-threaded.wasm", scope.location.href).href };

/** A macrotask yield: messages already queued for the worker are handled before it resolves. */
function macrotaskYield(): () => Promise<void> {
  const ch = new MessageChannel();
  const waiting: (() => void)[] = [];
  ch.port1.onmessage = () => waiting.shift()?.();
  return () =>
    new Promise<void>((resolve) => {
      waiting.push(resolve);
      ch.port2.postMessage(0);
    });
}

async function createSession(model: Uint8Array): Promise<Session> {
  const s = await ort.InferenceSession.create(model, { executionProviders: ["wasm"], graphOptimizationLevel: "all" });
  return {
    async run(planes: Float32Array) {
      const out = await s.run({ planes: new ort.Tensor("float32", planes, [1, 19, 8, 8]) });
      const policy = out.policy?.data;
      const wdl = out.wdl?.data;
      if (!(policy instanceof Float32Array) || !(wdl instanceof Float32Array)) throw new Error("model outputs policy and wdl must be float32");
      return { policy, wdl };
    },
  };
}

const core = new EngineCore((msg) => scope.postMessage(msg), {
  fetch: (url) => fetch(url, { credentials: "same-origin" }),
  subtle: scope.crypto?.subtle,
  now: () => performance.now(),
  yieldNow: macrotaskYield(),
  createSession,
  baseUrl: scope.location.href,
});

scope.onmessage = (ev: MessageEvent) => {
  void core.handle(ev.data);
};
core.ready();
