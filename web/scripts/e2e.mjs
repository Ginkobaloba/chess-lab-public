// Provenance: harness approach adapted from Ginkobaloba/draughts-lab
// web/scripts/e2e.mjs at commit 0a5c5a0fe6cc3443565937a738509f5de9479b19
// (Paradigm-owned, MIT): the in-process static server, playwright-core with an
// installed Chromium, PASS/FAIL lines, console-error and request capture, a
// JSON result file. The checks are new.
//
// Playwright checks for the dev page (local only; not part of CI).
//
//   node scripts/e2e.mjs [--out ../receipts/web-v1/e2e.json] [--phase all|timing] [--headed]
//
// Needs dist/ (npm run build), the exported models (scripts/export_web.py, served
// from D:/chess-lab-data/export or CHESS_LAB_EXPORT at /model/) and a Chromium
// build for playwright-core 1.60.0 (npx playwright-core install chromium, or an
// existing ms-playwright cache).
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { cpus } from "node:os";
import { dirname, join, resolve } from "node:path";
import { parseArgs } from "node:util";
import { Chess } from "chess.js";
import { chromium } from "playwright-core";
import { MODELS_DEFAULT, WEB_ROOT, startServer } from "./serve.mjs";

const { values } = parseArgs({
  options: {
    phase: { type: "string", default: "all" },
    port: { type: "string", default: "0" },
    models: { type: "string", default: MODELS_DEFAULT },
    out: { type: "string" },
    headed: { type: "boolean", default: false },
  },
});

const ATOL = 1e-3;
const parity = JSON.parse(readFileSync(join(WEB_ROOT, "../receipts/web-v1/parity.json"), "utf8"));
const modelManifest = JSON.parse(readFileSync(join(values.models, "manifest.json"), "utf8"));

const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? "PASS" : "FAIL"} ${what}`);
  if (!ok) failures.push(what);
};

const server = await startServer(Number(values.port), values.models);
const base = `http://localhost:${server.address().port}`;
const browser = await chromium.launch({ headless: !values.headed });
console.log(`chromium ${browser.version()} at ${base}`);
let commit = "unknown";
try {
  commit = execFileSync("git", ["rev-parse", "HEAD"], { cwd: WEB_ROOT, encoding: "utf8" }).trim();
} catch {
  // not a git checkout
}
const results = {
  schema: "chess-lab/web-e2e/v1",
  generator: "web/scripts/e2e.mjs",
  phase: values.phase,
  commit,
  chromium: browser.version(),
  node: process.version,
  host: { cpu: cpus()[0]?.model, logical_cpus: cpus().length },
  checks: [],
  runs: {},
};

async function openPage(query) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const consoleErrors = [];
  const responses = [];
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));
  // Worker fetches are reported on the context, not the page.
  context.on("response", (r) => {
    const len = r.headers()["content-length"];
    responses.push({ path: new URL(r.url()).pathname, status: r.status(), bytes: len === undefined ? null : Number(len) });
  });
  await page.goto(`${base}/demo/${query}`);
  await page.waitForFunction(() => document.body.dataset.ready === "true" || document.body.dataset.loadError !== undefined, null, { timeout: 120_000 });
  const loadError = await page.evaluate(() => document.body.dataset.loadError ?? null);
  return { context, page, consoleErrors, responses, loadError };
}

/** Top-1 move, logit and network time for every parity position, computed in the page's worker. */
async function evalAll(page, fens) {
  return page.evaluate(async (list) => {
    const out = [];
    for (const fen of list) {
      const e = await window.__lab.client.bestMove({ fen }).done;
      out.push({ move: e.move, logit: e.logit, evalMs: e.evalMs });
    }
    return out;
  }, fens);
}

const stats = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  const q = (p) => s[Math.min(s.length - 1, Math.floor(p * s.length))];
  return { n: s.length, median: q(0.5), p90: q(0.9), max: s[s.length - 1] };
};

try {
  const fp = await openPage("?model=fp32");
  check(fp.loadError === null, `dev page loaded the fp32 model (${fp.loadError ?? "ok"})`);
  const model = await fp.page.evaluate(() => window.__lab.model);
  const fpEntry = modelManifest.models.find((m) => m.id === "fp32");
  check(model?.sha256 === parity.reexport.sha256 && model?.sha256 === parity.rated_onnx.sha256, `the worker verified and loaded the rated bytes (sha256 ${model?.sha256?.slice(0, 16)})`);

  const fens = parity.per_position.map((p) => p.fen);
  if (values.phase === "all") {
    // 1. A legal model move for the start position, the same one Python onnxruntime picks.
    const start = await fp.page.evaluate(async () => {
      const e = await window.__lab.client.bestMove({ moves: [] }).done;
      return { move: e.move, san: e.san, legalCount: e.legalCount, wdl: e.wdl };
    });
    const legal = new Chess().moves({ verbose: true }).map((m) => `${m.from}${m.to}${m.promotion ?? ""}`);
    const pyStart = parity.per_position.find((p) => p.name === "start");
    check(legal.includes(start.move), `start position: model move ${start.move} (${start.san}) is legal (${start.legalCount} legal moves)`);
    check(start.move === pyStart.top1, `start position: same move as Python onnxruntime (${pyStart.top1})`);
    results.runs.start = start;

    // 2. Cancel: a queued request by id, and one posted just before its cancel.
    const cancel = await fp.page.evaluate(async () => {
      const c = window.__lab.client;
      const a = c.bestMove({ moves: ["e2e4"] });
      const b = c.bestMove({ moves: ["d2d4"] });
      c.cancel(b.id);
      const [ra, rb] = await Promise.all([a.done, b.done]);
      const d = c.bestMove({ moves: ["c2c4"] });
      c.cancel(d.id);
      const rd = await d.done;
      const after = await c.bestMove({ moves: ["g1f3"] }).done;
      return { a: ra?.move ?? null, b: rb, d: rd, after: after?.move ?? null };
    });
    check(cancel.b === null && cancel.a !== null, `cancel(id) dropped the queued request only (other request played ${cancel.a})`);
    check(cancel.d === null, "cancel(id) posted right after its request wins (request ended cancelled)");
    check(cancel.after !== null, `the worker keeps serving after cancels (${cancel.after})`);
    results.runs.cancel = cancel;

    // 3. Browser parity: onnxruntime-web in Chromium vs Python onnxruntime on every parity position.
    const got = await evalAll(fp.page, fens);
    let same = 0;
    let checked = 0;
    let maxDiff = 0;
    const mismatches = [];
    parity.per_position.forEach((p, i) => {
      maxDiff = Math.max(maxDiff, Math.abs(got[i].logit - p.logit));
      if (p.margin === null || p.margin > 2 * ATOL) {
        checked++;
        if (got[i].move === p.top1) same++;
        else mismatches.push({ name: p.name, python: p.top1, browser: got[i].move });
      }
    });
    check(same === checked && maxDiff <= ATOL, `browser top-1 equals Python onnxruntime on ${same}/${checked} positions; max |top-1 logit diff| ${maxDiff.toExponential(2)} (tolerance ${ATOL})`);
    results.runs.parity = { positions: fens.length, checked, same, max_abs_top1_logit_diff: maxDiff, tolerance: ATOL, mismatches };
    results.runs.fp32_eval_ms = stats(got.map((g) => g.evalMs));

    // 4. The board: a person's move gets a model reply.
    await fp.page.click('[data-square="e2"]');
    await fp.page.click('[data-square="e4"]');
    await fp.page.waitForFunction(() => document.body.dataset.ply === "2", null, { timeout: 30_000 });
    const status = await fp.page.textContent("#status");
    check(/Model played/.test(status ?? ""), `board: after e2e4 the model replied ("${status}")`);
    mkdirSync(join(WEB_ROOT, "test-results"), { recursive: true });
    await fp.page.screenshot({ path: join(WEB_ROOT, "test-results/dev-page.png"), fullPage: true });

    check(fp.consoleErrors.length === 0, `no console errors (${fp.consoleErrors.join(" | ") || "none"})`);
    const byPath = (re) => fp.responses.filter((r) => re.test(r.path));
    const fetched = {
      loader_and_page: byPath(/\/(dist\/dev\.js|demo\/)$/),
      worker: byPath(/chess-lab-worker\.js$/),
      wasm: byPath(/\.wasm$/),
      glue_mjs: byPath(/\.mjs$/),
      model: byPath(/\.onnx$/),
    };
    check(fetched.wasm.length === 1 && fetched.wasm[0].path.endsWith("/dist/ort-wasm-simd-threaded.wasm"), `one wasm fetched, from dist/ (${fetched.wasm.map((r) => `${r.path} ${r.bytes}`).join(", ")})`);
    check(fetched.glue_mjs.length === 0, `no separate .mjs glue fetched (the wasm-only bundle inlines it): ${fetched.glue_mjs.length}`);
    check(fetched.model.length === 1 && fetched.model[0].bytes === fpEntry.bytes, `one model fetched, ${fetched.model[0]?.bytes} bytes`);
    results.runs.fetched = fetched;
  } else {
    const got = await evalAll(fp.page, fens);
    results.runs.fp32_eval_ms = stats(got.map((g) => g.evalMs));
  }

  // 5. The other exported files (NOT the rated model): do they load in onnxruntime-web,
  // how often do they pick the fp32 file's move, how fast are they. Information, not checks.
  for (const extra of modelManifest.models.filter((m) => m.id !== "fp32")) {
    const q = await openPage(`?model=${extra.id}`);
    if (q.loadError !== null) {
      results.runs[extra.id] = { loaded: false, error: q.loadError };
      console.log(`INFO ${extra.id} did not load in onnxruntime-web: ${q.loadError}`);
    } else {
      const got = await evalAll(q.page, fens);
      const agree = got.filter((g, i) => g.move === parity.per_position[i].top1).length;
      results.runs[extra.id] = { loaded: true, bytes: extra.bytes, top1_same_as_fp32: agree, positions: fens.length, eval_ms: stats(got.map((g) => g.evalMs)) };
      console.log(`INFO ${extra.id} (unrated): top-1 same as fp32 on ${agree}/${fens.length}; median network ${results.runs[extra.id].eval_ms.median.toFixed(2)} ms`);
    }
    await q.context.close();
  }
  console.log(`INFO fp32 median network ${results.runs.fp32_eval_ms.median.toFixed(2)} ms, p90 ${results.runs.fp32_eval_ms.p90.toFixed(2)} ms over ${fens.length} positions`);
  await fp.context.close();
} catch (err) {
  check(false, `e2e crashed: ${err instanceof Error ? err.stack : String(err)}`);
} finally {
  await browser.close();
  server.close();
}

results.checks = failures.length === 0 ? "all passed" : failures;
if (values.out) {
  const out = resolve(values.out);
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, `${JSON.stringify(results, null, 1)}\n`);
  console.log(`results: ${out}`);
}
console.log(failures.length === 0 ? "e2e: all checks passed" : `e2e: ${failures.length} failed`);
process.exit(failures.length === 0 ? 0 : 1);
