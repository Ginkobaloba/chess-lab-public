/**
 * Worker message protocol, version 1 (web/README.md, "Message protocol").
 *
 * Shape adapted from Ginkobaloba/draughts-lab web/src/protocol.ts at commit
 * 0a5c5a0fe6cc3443565937a738509f5de9479b19 (Paradigm-owned, MIT): versioned
 * messages, caller-chosen request ids, one terminal event per request, a
 * targeted `cancel`. The request and event types are new (chess).
 *
 * Every message in either direction is an object with `v: 1`. Requests carry a
 * caller-chosen `id`; every event the worker sends in answer carries the same
 * `id`. Each request except `cancel` ends with exactly one terminal event:
 * `loaded`, `bestMove`, `cancelled` or `error`. `cancel` has no reply of its
 * own. The worker sends `{ type: "ready", protocol: 1, id: 0 }` when it starts.
 *
 * `bestMove` requests run one at a time in arrival order. A single network
 * evaluation cannot be interrupted, so `cancel { target }` works like this: a
 * queued request is dropped and ends with `cancelled` at once; a request whose
 * evaluation is in flight ends with `cancelled` when the evaluation returns,
 * and its result is thrown away. Every request yields to the message queue
 * once before it evaluates, so a `cancel` posted right after a `bestMove`
 * always wins. `cancel` without `target` cancels every queued and running
 * request.
 *
 * This file holds types and constants only, so the page-side client imports it
 * for next to nothing.
 */

export const PROTOCOL_VERSION = 1;

/** Longest move list a `bestMove` request may carry (plies from its start position). */
export const MAX_MOVES = 1000;

export interface ModelInfo {
  readonly id: string;
  readonly file: string;
  readonly bytes: number;
  readonly sha256: string;
  /** True only for the exact bytes that were rated on the engine ladder. */
  readonly rated: boolean;
  readonly step: number | null;
}

export type Request =
  /** Fetch the manifest, then the model `model` from it; check bytes and sha256; create the session. */
  | { readonly type: "load"; readonly manifestUrl: string; readonly model: string }
  /**
   * The model's move in the position reached from `fen` (the standard start
   * position when left out) by playing `moves` (UCI text, at most MAX_MOVES).
   */
  | { readonly type: "bestMove"; readonly fen?: string; readonly moves?: readonly string[] }
  /** Stop request `target` (every queued and running request when left out). */
  | { readonly type: "cancel"; readonly target?: number };

export type RequestMessage = Request & { readonly v: typeof PROTOCOL_VERSION; readonly id: number };

export interface BestMoveEvent {
  readonly type: "bestMove";
  /** UCI text (e2e4, e7e8q). */
  readonly move: string;
  readonly san: string;
  /** Policy index, from * 64 + to in the side-to-move frame. */
  readonly index: number;
  readonly logit: number;
  /** Best legal logit minus the second best (Infinity with one legal move). */
  readonly margin: number;
  /** Legal moves that have a policy index (under-promotions are never played). */
  readonly legalCount: number;
  /** Up to five best legal moves with their logits. */
  readonly top: readonly { readonly uci: string; readonly logit: number }[];
  /** Softmax of the value head, from the side to move: win, draw, loss. */
  readonly wdl: readonly [number, number, number];
  /** The position that was evaluated. */
  readonly fen: string;
  /** Wall time of the network evaluation alone. */
  readonly evalMs: number;
}

export type Event =
  | { readonly type: "ready"; readonly protocol: typeof PROTOCOL_VERSION }
  | { readonly type: "loaded"; readonly model: ModelInfo; readonly loadMs: number }
  | BestMoveEvent
  | { readonly type: "cancelled" }
  | { readonly type: "error"; readonly message: string };

export type EventMessage = Event & { readonly v: typeof PROTOCOL_VERSION; readonly id: number };

export const TERMINAL_TYPES: ReadonlySet<string> = new Set(["loaded", "bestMove", "cancelled", "error"]);

export function isEventMessage(x: unknown): x is EventMessage {
  return typeof x === "object" && x !== null && (x as { v?: unknown }).v === PROTOCOL_VERSION && typeof (x as { type?: unknown }).type === "string";
}
