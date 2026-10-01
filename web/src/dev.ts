/**
 * Local dev page (demo/index.html): play against the model in this tab.
 * Engineering only: not a design for /lab/chess and not site copy. Its text
 * shows no rating and is not for approval. Built into dist/dev.js, which is
 * not part of the release tarball.
 *
 * Query: ?model=fp32|int8 (default fp32, the rated file), ?side=w|b (default w).
 * The page exposes `window.__lab` for scripts/e2e.mjs.
 */
import { Chess, type Square } from "chess.js";
import { EngineClient } from "./client.js";
import type { BestMoveEvent, ModelInfo } from "./protocol.js";

const GLYPH: Record<string, string> = { wp: "♙", wn: "♘", wb: "♗", wr: "♖", wq: "♕", wk: "♔", bp: "♟", bn: "♞", bb: "♝", br: "♜", bq: "♛", bk: "♚" };
const NAME: Record<string, string> = { p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king" };

const params = new URLSearchParams(location.search);
const modelId = params.get("model") ?? "fp32";
let human: "w" | "b" = params.get("side") === "b" ? "b" : "w";

const client = new EngineClient(new URL("../dist/chess-lab-worker.js", location.href));
let chess = new Chess();
let moves: string[] = [];
let selected: Square | null = null;
let thinking: number | null = null;
let model: ModelInfo | null = null;
const log: BestMoveEvent[] = [];

const $ = (id: string) => document.getElementById(id) as HTMLElement;
const boardEl = $("board");
const statusEl = $("status");

function status(text: string): void {
  statusEl.textContent = text;
}

function render(): void {
  boardEl.replaceChildren();
  const legalTargets = new Set(selected === null ? [] : chess.moves({ square: selected, verbose: true }).map((m) => m.to));
  for (let r = 0; r < 8; r++) {
    for (let f = 0; f < 8; f++) {
      const file = human === "w" ? f : 7 - f;
      const rank = human === "w" ? 7 - r : r;
      const sq = `${"abcdefgh"[file]}${rank + 1}` as Square;
      const p = chess.get(sq);
      const b = document.createElement("button");
      b.type = "button";
      b.className = `sq ${(file + rank) % 2 === 0 ? "dark" : "light"}${sq === selected ? " sel" : ""}${legalTargets.has(sq) ? " target" : ""}`;
      b.dataset.square = sq;
      b.textContent = p ? (GLYPH[p.color + p.type] ?? "") : "";
      b.setAttribute("aria-label", p ? `${sq}, ${p.color === "w" ? "white" : "black"} ${NAME[p.type]}` : sq);
      b.addEventListener("click", () => onSquare(sq));
      boardEl.append(b);
    }
  }
  document.body.dataset.ply = String(moves.length);
}

function gameOverText(): string | null {
  if (chess.isCheckmate()) return `Checkmate, ${chess.turn() === "w" ? "Black" : "White"} wins.`;
  if (chess.isDraw()) return "Draw.";
  return null;
}

function onSquare(sq: Square): void {
  if (thinking !== null || chess.turn() !== human || gameOverText() !== null) return;
  const p = chess.get(sq);
  if (selected === null || (p && p.color === human)) {
    selected = p && p.color === human ? sq : null;
    render();
    return;
  }
  const legal = chess.moves({ square: selected, verbose: true }).find((m) => m.to === sq);
  selected = null;
  if (legal === undefined) {
    render();
    return;
  }
  // Dev page: promotions are always to a queen.
  const m = chess.move({ from: legal.from, to: legal.to, promotion: legal.promotion ? "q" : undefined });
  moves.push(`${m.from}${m.to}${m.promotion ?? ""}`);
  render();
  void engineTurn();
}

async function engineTurn(): Promise<void> {
  const over = gameOverText();
  if (over !== null) {
    status(over);
    return;
  }
  if (chess.turn() === human) {
    status("Your move.");
    return;
  }
  const req = client.bestMove({ moves });
  thinking = req.id;
  status("Model is choosing a move.");
  try {
    const e = await req.done;
    if (thinking !== req.id) return; // superseded by a new game
    thinking = null;
    if (e === null) {
      status("Cancelled.");
      return;
    }
    log.push(e);
    chess.move({ from: e.move.slice(0, 2), to: e.move.slice(2, 4), promotion: e.move[4] });
    moves.push(e.move);
    render();
    const done = gameOverText();
    status(done ?? `Model played ${e.san} (network ${e.evalMs.toFixed(1)} ms). Your move.`);
  } catch (err) {
    thinking = null;
    status(`Error: ${err instanceof Error ? err.message : String(err)}`);
  }
}

function newGame(side: "w" | "b"): void {
  if (thinking !== null) client.cancel(thinking);
  thinking = null;
  human = side;
  chess = new Chess();
  moves = [];
  selected = null;
  render();
  void engineTurn();
}

$("new-white").addEventListener("click", () => newGame("w"));
$("new-black").addEventListener("click", () => newGame("b"));

(window as unknown as { __lab: unknown }).__lab = { client, Chess, log, get model() { return model; }, get moves() { return moves; }, newGame };

render();
status("Loading the model.");
client
  .load("../model/manifest.json", modelId)
  .then((r) => {
    model = r.model;
    $("model-info").textContent = `Model ${r.model.id}, ${r.model.bytes.toLocaleString("en-US")} bytes, sha256 ${r.model.sha256.slice(0, 12)}, ${r.model.rated ? "the rated file" : "not the rated file"}; loaded in ${r.loadMs.toFixed(0)} ms.`;
    document.body.dataset.ready = "true";
    void engineTurn();
  })
  .catch((err: unknown) => {
    document.body.dataset.loadError = String(err);
    status(`Model load failed: ${err instanceof Error ? err.message : String(err)}`);
  });
