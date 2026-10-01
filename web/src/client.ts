/**
 * Page-side client for the worker (dist/chess-lab.js). No engine, chess.js or
 * onnxruntime code: the worker loads those on first use.
 *
 * Adapted from `LabClient` in Ginkobaloba/draughts-lab web/src/viewer.ts at
 * commit 0a5c5a0fe6cc3443565937a738509f5de9479b19 (Paradigm-owned, MIT):
 * lazy module worker, request ids, one pending entry per request resolved by
 * its terminal event, a failed worker rejects everything pending and is
 * replaced on the next request, targeted `cancel(id)`.
 */
import type { BestMoveEvent, EventMessage, ModelInfo, Request } from "./protocol.js";
import { PROTOCOL_VERSION, TERMINAL_TYPES, isEventMessage } from "./protocol.js";

export type Terminal = Extract<EventMessage, { type: "loaded" | "bestMove" | "cancelled" }>;

export class EngineClient {
  private worker: Worker | null = null;
  private nextId = 1;
  private readonly pending = new Map<number, { resolve: (e: Terminal) => void; reject: (err: Error) => void }>();

  constructor(private readonly workerUrl: string | URL) {}

  get started(): boolean {
    return this.worker !== null;
  }

  private ensure(): Worker {
    if (this.worker === null) {
      const w = new Worker(this.workerUrl, { type: "module", name: "chess-lab" });
      w.onmessage = (ev: MessageEvent) => this.dispatch(ev.data);
      w.onerror = (ev: ErrorEvent) => {
        // A worker that failed (for example its script did not load) never answers again:
        // drop it so the next request starts a fresh one instead of waiting forever.
        if (this.worker === w) this.worker = null;
        w.terminate();
        for (const p of this.pending.values()) p.reject(new Error(ev.message || "worker error"));
        this.pending.clear();
      };
      this.worker = w;
    }
    return this.worker;
  }

  private dispatch(data: unknown): void {
    if (!isEventMessage(data)) return;
    const p = this.pending.get(data.id);
    if (p === undefined || !TERMINAL_TYPES.has(data.type)) return;
    this.pending.delete(data.id);
    if (data.type === "error") p.reject(new Error(data.message));
    else p.resolve(data as Terminal);
  }

  /** Sends a request; returns its id (for `cancel`) and a promise of its terminal event. */
  start(req: Request): { readonly id: number; readonly done: Promise<Terminal> } {
    const id = this.nextId++;
    const worker = this.ensure();
    const done = new Promise<Terminal>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      worker.postMessage({ ...req, v: PROTOCOL_VERSION, id });
    });
    return { id, done };
  }

  /** Loads and verifies a model from a `chess-lab/web-model/v1` manifest. */
  async load(manifestUrl: string, model = "fp32"): Promise<{ model: ModelInfo; loadMs: number }> {
    const e = await this.start({ type: "load", manifestUrl, model }).done;
    if (e.type !== "loaded") throw new Error(`load ended with ${e.type}`);
    return { model: e.model, loadMs: e.loadMs };
  }

  /** The model's move after `moves` (UCI) from `fen` (default: the start position); null if cancelled. */
  bestMove(position: { fen?: string; moves?: readonly string[] }): { readonly id: number; readonly done: Promise<BestMoveEvent | null> } {
    const { id, done } = this.start({ type: "bestMove", ...position });
    return { id, done: done.then((e) => (e.type === "bestMove" ? e : null)) };
  }

  /** Stops request `target`; without it, every queued and running request. */
  cancel(target?: number): void {
    if (this.worker === null) return;
    this.worker.postMessage({ type: "cancel", ...(target === undefined ? {} : { target }), v: PROTOCOL_VERSION, id: this.nextId++ });
  }

  destroy(): void {
    this.worker?.terminate();
    this.worker = null;
    for (const p of this.pending.values()) p.reject(new Error("client destroyed"));
    this.pending.clear();
  }
}
