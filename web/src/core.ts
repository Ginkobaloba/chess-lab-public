/**
 * The worker's logic, independent of the worker global and of onnxruntime so
 * Node tests can drive it with a fake session: `new EngineCore(post, env).handle(message)`.
 *
 * Structure adapted from Ginkobaloba/draughts-lab web/src/core.ts at commit
 * 0a5c5a0fe6cc3443565937a738509f5de9479b19 (Paradigm-owned, MIT): the
 * injected environment, the version check and error envelope in `handle`,
 * and the manifest load that checks the file's directory, byte count and
 * sha256 before use. The request queue and the chess logic are new.
 */
import { Chess } from "chess.js";
import { compact, legalIndexed, pickMove, planes, playUci } from "./encode.js";
import type { BestMoveEvent, Event, ModelInfo, RequestMessage } from "./protocol.js";
import { MAX_MOVES, PROTOCOL_VERSION } from "./protocol.js";

export const MANIFEST_SCHEMA = "chess-lab/web-model/v1";
export const ENCODING = "chess-lab/encode/v1";

/** One network evaluation: 1 x 19 x 8 x 8 planes in, 4096 policy logits and 3 WDL logits out. */
export interface Session {
  run(planes: Float32Array): Promise<{ readonly policy: Float32Array; readonly wdl: Float32Array }>;
}

export interface CoreEnv {
  readonly fetch: (url: string) => Promise<{ ok: boolean; status: number; arrayBuffer(): Promise<ArrayBuffer>; json(): Promise<unknown> }>;
  /** `crypto.subtle`; undefined outside secure contexts. */
  readonly subtle: Pick<SubtleCrypto, "digest"> | undefined;
  readonly now: () => number;
  /** Resolves after pending messages have been handled (a macrotask). */
  readonly yieldNow: () => Promise<void>;
  readonly createSession: (model: Uint8Array) => Promise<Session>;
  /** Base for relative manifest URLs (the worker's location). */
  readonly baseUrl?: string;
}

interface ManifestModel {
  readonly id: string;
  readonly file: string;
  readonly bytes: number;
  readonly sha256: string;
  readonly rated?: boolean;
  readonly step?: number;
}

interface Job {
  readonly id: number;
  cancelled: boolean;
  readonly run: () => Promise<Event>;
}

function hex(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

function softmax3(z: Float32Array): [number, number, number] {
  const m = Math.max(z[0] as number, z[1] as number, z[2] as number);
  const e = [0, 1, 2].map((i) => Math.exp((z[i] as number) - m));
  const s = (e[0] as number) + (e[1] as number) + (e[2] as number);
  return [(e[0] as number) / s, (e[1] as number) / s, (e[2] as number) / s];
}

/** Throws unless a `bestMove` request is well formed; returns the position it names. */
export function positionOf(msg: { fen?: unknown; moves?: unknown }): Chess {
  if (msg.fen !== undefined && typeof msg.fen !== "string") throw new Error("bestMove: fen must be a string");
  const moves = msg.moves ?? [];
  if (!Array.isArray(moves) || !moves.every((m) => typeof m === "string")) throw new Error("bestMove: moves must be an array of strings");
  if (moves.length > MAX_MOVES) throw new Error(`bestMove: at most ${MAX_MOVES} moves`);
  let chess: Chess;
  try {
    chess = msg.fen === undefined ? new Chess() : new Chess(msg.fen as string);
  } catch (err) {
    throw new Error(`bestMove: invalid FEN (${err instanceof Error ? err.message : String(err)})`);
  }
  for (const m of moves as string[]) playUci(chess, m);
  return chess;
}

export class EngineCore {
  private session: Session | null = null;
  private model: ModelInfo | null = null;
  private readonly queue: Job[] = [];
  private running: Job | null = null;

  constructor(
    private readonly post: (msg: Event & { v: typeof PROTOCOL_VERSION; id: number }) => void,
    private readonly env: CoreEnv,
  ) {}

  private send(id: number, ev: Event): void {
    this.post({ ...ev, v: PROTOCOL_VERSION, id });
  }

  ready(): void {
    this.send(0, { type: "ready", protocol: PROTOCOL_VERSION });
  }

  get loadedModel(): ModelInfo | null {
    return this.model;
  }

  async handle(raw: unknown): Promise<void> {
    const msg = raw as RequestMessage;
    const id = typeof msg?.id === "number" ? msg.id : -1;
    if (msg === null || typeof msg !== "object" || msg.v !== PROTOCOL_VERSION) {
      this.send(id, { type: "error", message: `unsupported message (protocol ${PROTOCOL_VERSION} expected)` });
      return;
    }
    try {
      switch (msg.type) {
        case "cancel":
          if (msg.target !== undefined && !Number.isSafeInteger(msg.target)) throw new Error("cancel: target must be a request id");
          this.cancel(msg.target);
          return;
        case "load":
          if (typeof msg.manifestUrl !== "string") throw new Error("load: manifestUrl must be a string");
          if (typeof msg.model !== "string") throw new Error("load: model must be a string");
          await this.load(id, msg.manifestUrl, msg.model);
          return;
        case "bestMove": {
          // Checked before it is queued, so a malformed request never waits behind others.
          const chess = positionOf(msg);
          this.enqueue({ id, cancelled: false, run: () => this.bestMove(chess) });
          return;
        }
        default:
          this.send(id, { type: "error", message: `unknown request type ${JSON.stringify((msg as { type?: unknown }).type)}` });
      }
    } catch (err) {
      this.send(id, { type: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }

  private cancel(target: number | undefined): void {
    const hit = (j: Job) => target === undefined || j.id === target;
    for (let i = this.queue.length - 1; i >= 0; i--) {
      const job = this.queue[i] as Job;
      if (hit(job)) {
        this.queue.splice(i, 1);
        this.send(job.id, { type: "cancelled" });
      }
    }
    // The in-flight evaluation finishes, then reports `cancelled` instead of its result.
    if (this.running !== null && hit(this.running)) this.running.cancelled = true;
  }

  private enqueue(job: Job): void {
    this.queue.push(job);
    if (this.running === null) void this.drain();
  }

  private async drain(): Promise<void> {
    while (this.queue.length > 0) {
      const job = this.queue.shift() as Job;
      this.running = job;
      try {
        // Let messages already posted (a cancel for this job) arrive first.
        await this.env.yieldNow();
        if (job.cancelled) {
          this.send(job.id, { type: "cancelled" });
          continue;
        }
        const ev = await job.run();
        this.send(job.id, job.cancelled ? { type: "cancelled" } : ev);
      } catch (err) {
        this.send(job.id, { type: "error", message: err instanceof Error ? err.message : String(err) });
      } finally {
        this.running = null;
      }
    }
  }

  private async bestMove(chess: Chess): Promise<BestMoveEvent> {
    const session = this.session;
    if (session === null) throw new Error("no model loaded (send load first)");
    const legal = legalIndexed(chess);
    if (legal.length === 0) throw new Error("no legal moves (checkmate or stalemate)");
    const x = planes(compact(chess));
    const t0 = this.env.now();
    const out = await session.run(x);
    const evalMs = this.env.now() - t0;
    if (out.policy.length !== 4096 || out.wdl.length !== 3) throw new Error(`model output shapes ${out.policy.length}, ${out.wdl.length}; expected 4096, 3`);
    const pick = pickMove(legal, out.policy);
    return {
      type: "bestMove",
      move: pick.best.uci,
      san: pick.best.san,
      index: pick.best.index,
      logit: pick.logit,
      margin: pick.margin,
      legalCount: legal.length,
      top: pick.top,
      wdl: softmax3(out.wdl),
      fen: chess.fen(),
      evalMs,
    };
  }

  private async load(id: number, manifestUrl: string, modelId: string): Promise<void> {
    const t0 = this.env.now();
    const url = new URL(manifestUrl, this.env.baseUrl).href;
    const res = await this.env.fetch(url);
    if (!res.ok) throw new Error(`manifest ${url}: HTTP ${res.status}`);
    const manifest = (await res.json()) as { schema?: string; encoding?: string; models?: ManifestModel[] };
    if (manifest.schema !== MANIFEST_SCHEMA || !Array.isArray(manifest.models)) throw new Error(`manifest ${url} is not ${MANIFEST_SCHEMA}`);
    if (manifest.encoding !== ENCODING) throw new Error(`manifest encoding ${JSON.stringify(manifest.encoding)}; this worker speaks ${ENCODING}`);
    const entry = manifest.models.find((m) => m.id === modelId);
    if (entry === undefined) throw new Error(`manifest has no model ${JSON.stringify(modelId)}`);
    if (typeof entry.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(entry.sha256)) throw new Error(`model ${entry.id} has no valid sha256`);
    if (typeof entry.file !== "string") throw new Error(`model ${entry.id} has no file`);
    const fileUrl = new URL(entry.file, url);
    const dir = new URL(".", url);
    // Model files live next to (or below) their manifest, on its origin.
    if (fileUrl.origin !== dir.origin || !fileUrl.pathname.startsWith(dir.pathname)) {
      throw new Error(`model ${entry.id}: file ${JSON.stringify(entry.file)} is outside the manifest's directory`);
    }
    const subtle = this.env.subtle;
    if (subtle === undefined) throw new Error("crypto.subtle is unavailable (the page must be served over https or from localhost)");
    const r = await this.env.fetch(fileUrl.href);
    if (!r.ok) throw new Error(`${fileUrl.href}: HTTP ${r.status}`);
    const bytes = await r.arrayBuffer();
    if (bytes.byteLength !== entry.bytes) throw new Error(`${entry.id}: ${bytes.byteLength} bytes, manifest says ${entry.bytes}`);
    const digest = hex(await subtle.digest("SHA-256", bytes));
    if (digest !== entry.sha256) throw new Error(`${entry.id}: sha256 ${digest} does not match the manifest`);
    this.session = await this.env.createSession(new Uint8Array(bytes));
    this.model = { id: entry.id, file: entry.file, bytes: entry.bytes, sha256: entry.sha256, rated: entry.rated === true, step: entry.step ?? null };
    this.send(id, { type: "loaded", model: this.model, loadMs: this.env.now() - t0 });
  }
}
