# @chess-lab/web: browser build prep

Engineering prep for a future `/lab/chess` page: the chess-lab network runs in
the browser through onnxruntime-web inside a Web Worker, with chess.js for
legal moves and an encoder that matches `chesslab/encode.py` exactly. The
architecture follows draughts-lab's `web/` bundle (versioned worker protocol,
request ids, targeted cancel, a page-side client, pack/serve/e2e scripts);
files adapted from it carry a provenance header naming the source file and
commit.

**Not included on purpose:** public copy, any rating number or rating display,
the `/lab/chess` page itself, and any paradigm-site change. Those are
deferred (docs/LICENSES.md; rating label in the top-level README). The dev page below is
for local testing only; its text is not site copy.

## What ships

Sizes from `receipts/web-v1/bundle-size.json` (written by
`node scripts/pack.mjs --receipt ...`; gzip level 9 and brotli quality 11):

| File | Loaded | Contents | bytes | gzip | brotli |
|---|---|---|---|---|---|
| `dist/chess-lab.js` | with the page | worker client, protocol constants | 1,599 | 786 | 691 |
| `dist/chess-lab-worker.js` | on the first `load` | onnxruntime-web 1.30.0 (wasm backend JS), chess.js 1.4.0, encoder, worker core | 117,469 | 40,143 | 35,104 |
| `dist/ort-wasm-simd-threaded.wasm` | by the worker | the onnxruntime-web WebAssembly runtime | 14,239,897 | 3,687,160 | 2,355,011 |
| `sup-v1-final.onnx` (fp32, the rated file) | by the worker | the model, from `D:\chess-lab-data\export` | 6,014,759 | 5,585,440 | 5,524,136 |
| `sup-v1-final.fp16w.onnx` (NOT rated) | optional | the same net, weights stored as float16 | 3,016,025 | 2,789,104 | 2,655,498 |
| `sup-v1-final.int8.onnx` (NOT rated) | optional | int8 weights | 1,548,347 | 970,634 | 919,549 |

First move with the rated model: 20,373,724 bytes raw, 9,313,529 gzip,
7,914,942 brotli (`totals.first_move` in the receipt). The model barely
compresses; the wasm runtime is most of the rest. With the fp16-weight file
instead it would be 6,517,193 gzip (`totals.first_move_by_model`), but that
file is not rated. `dist/dev.js` (the dev
page) is not released.

`dist/THIRD_PARTY_NOTICES.txt` lists the licenses of the bundled packages
(from esbuild's metafile), and `release/chess-lab-web-<version>.tgz` holds the
shipped files and `manifest.json` (deterministic, as in draughts-lab).

## Encoding contract

`src/encode.ts` ports `chesslab/encode.py` (side-to-move frame, 67-byte
compact record, 19 x 8 x 8 float32 planes, policy index `from * 64 + to`,
queen promotions only). The contract is
`receipts/web-v1/encode_golden.json`, written by
`scripts/gen_encode_golden.py` from the Python encoder: 16 edge positions (en
passant legal, set but impossible, and pinned; castling rights with and
without the pieces; promotions; half-move clocks 99, 150 and 300; check,
checkmate, stalemate) and 48 seeded positions (ladder opening plus up to 60
random plies, `chesslab.webref.seeded_positions`). For every case
`test/encode.test.ts` requires the same compact bytes, the same SHA-256 of the
float32 planes, and the same legal moves with the same indices, from the FEN
and (for the seeded cases) from replaying the UCI moves.
`tests/test_web_golden.py` regenerates the file in memory and compares bytes.

Two rules that are easy to get wrong in a port, both covered by the golden:
the en-passant byte comes from the legal moves (python-chess
`has_legal_en_passant`), never from the FEN field; castling rights count only
with the king and rook on their squares (python-chess `clean_castling_rights`).

## Parity (model)

`scripts/export_web.py` (receipt `receipts/web-v1/parity.json`): the final
checkpoint re-exported with `chesslab.export.export_onnx` is byte-identical to
the rated `ckpt_080000.onnx` (sha256 `b45c625b...`). Against PyTorch fp32 on
269 positions (14 edge positions with legal moves and 256 seeded): max
policy logit difference 7.63e-5, max WDL difference 3.81e-6, same legal top-1
on 269 of 269 (tolerance 1e-3 on every logit).

In Chromium (`receipts/web-v1/e2e.json`): onnxruntime-web picks the same
top-1 as Python onnxruntime on 269 of 269 positions, max top-1 logit
difference 4.78e-6. `test/model.test.ts` repeats the check in Node through
onnxruntime-web's wasm backend when the export directory exists.

Other exported files are not the rated model and are not parity (agreement
only; fp32 is the default):

- **int8** (`--int8`): same top-1 as PyTorch fp32 on 242 of 269 positions in
  Python onnxruntime and as the fp32 file on 244 of 269 in onnxruntime-web
  (so int8 output also differs between the two runtimes). It is slower in the
  browser: median network time 29.6 ms against 4.4 ms for fp32 on the machine
  in the e2e receipt (about 6.7x; the earlier receipt at commit a1c6aea, same machine, gave
  39.8 ms against 4.5 ms). It saves download, not compute. PR #5 rates it on
  the ladder separately.
- **fp16 weights** (`--fp16`, `sup-v1-final.fp16w.onnx`): every weight stored
  as float16 with a Cast back to float32, so the arithmetic is float32. Same
  top-1 as PyTorch on 269 of 269 (max policy logit difference 0.046) and as
  the fp32 file on 269 of 269 in the browser, at the same speed (median
  4.3 ms), for half the model download. 269 positions are too few to call it
  the same player: it needs its own ladder rating before it replaces fp32.

## Message protocol (version 1)

Every message has `v: 1` and an `id`. The worker answers each request with
exactly one terminal event under the same `id`, except `cancel`, which has no
reply of its own. The worker sends `{ type: "ready", protocol: 1, id: 0 }`
when it starts.

| Request | Terminal |
|---|---|
| `load { manifestUrl, model }` | `loaded { model: { id, file, bytes, sha256, rated, step }, loadMs }` or `error` |
| `bestMove { fen?, moves? }` (start position when `fen` is left out; `moves` UCI, at most 1000) | `bestMove { move, san, index, logit, margin, legalCount, top, wdl, fen, evalMs }`, `cancelled` or `error` |
| `cancel { target? }` | none of its own (see below); a `target` that is not a safe integer gets `error` |

- `load` resolves `manifestUrl` against the worker's URL. The manifest
  (`chess-lab/web-model/v1`, written by `export_web.py`) must name encoding
  `chess-lab/encode/v1`. The model file must resolve inside the manifest's
  directory on its origin; the worker checks the byte count, then the sha256
  with `crypto.subtle` (secure contexts only: https or localhost), before it
  creates the session. `rated` is true only for the rated bytes.
- `bestMove` requests are checked when they arrive (FEN, move text, legality;
  a bad one gets `error` at once) and then run one at a time in arrival order.
  The worker plays the arg-max of the policy over legal moves (as the ladder's
  `net:` player does); under-promotions have no index and are never played.
  A position with no legal move gets `error`.
- `cancel { target }`: a queued request is dropped and ends with `cancelled`
  at once. One network evaluation cannot be interrupted, so a request already
  evaluating ends with `cancelled` when it returns and its result is thrown
  away. Every request yields to the message queue once before it evaluates,
  so a `cancel` posted right after its `bestMove` always wins. Without
  `target`, every queued and running request is cancelled.
- `load` is not queued; two `load`s in flight race (the page should wait for
  one before sending another).
- Differences from draughts-lab's protocol: no long jobs that replace each
  other (requests queue instead), and no match, human-game or training
  requests; the page keeps the game and asks for one move at a time.

onnxruntime-web runs on its WebAssembly backend with one thread
(`numThreads = 1`, `proxy = false`): threads need SharedArrayBuffer, which
needs cross-origin isolation (COOP and COEP headers) that a host page cannot
be assumed to send. The worker keeps the evaluation off the page's main
thread. `wasmPaths` points at the worker's own directory, so the wasm file
must sit next to the worker (same origin; a CSP needs `worker-src 'self'` and
`script-src 'wasm-unsafe-eval'`, VERIFY on the host).

## Commands

```
npm ci
npm run typecheck
npx vitest run                  # encoder golden, worker core (fake session), model parity in Node when the export exists
npm run build                   # dist/ and release/, prints sizes, enforces budgets
node scripts/pack.mjs --receipt ../receipts/web-v1/bundle-size.json
node scripts/serve.mjs          # http://localhost:4318/demo/ (?model=fp32|int8, ?side=w|b)
node scripts/e2e.mjs --out ../receipts/web-v1/e2e.json
# a slower device, approximated with a hard CPU cap around the whole process tree (Windows;
# copied from draughts-lab, not exercised in this PR)
powershell -File scripts/cpu-cap.ps1 -Cores 0.25 -Command 'node scripts/e2e.mjs --phase timing'
```

Python side (repo root, `PYTHONPATH=.`):

```
python scripts/export_web.py --int8 --receipt receipts/web-v1/parity.json
python scripts/gen_encode_golden.py
python -m pytest tests/test_web_golden.py
```

`serve.mjs` serves `web/` and the export directory
(`D:\chess-lab-data\export`, or `CHESS_LAB_EXPORT`) at `/model/`, so model
files are never copied into the repo. `e2e.mjs` uses `playwright-core` 1.60.0
and an installed Chromium for that version; it is not run in CI. Its checks:
the rated bytes load and verify, a legal start-position move equal to
Python's, a cancel of a queued request and of a request posted just before its
cancel, top-1 parity with Python onnxruntime on all 269 parity positions, a
move on the dev board gets a reply, no console errors, exactly one wasm and
one model fetched; plus the int8 agreement and timing, reported as
information.

## Open items

- The public page, its copy, and whether and how a rating appears on it
  (not decided yet).
- The repo is GPL-3.0 (`LICENSE`). The browser bundle itself has no
  third-party GPL code: chess.js is BSD-2-Clause, onnxruntime-web MIT
  (docs/LICENSES.md).
- ONNX Runtime's `ThirdPartyNotices.txt` for the native code in the wasm file
  must ship with any public release (VERIFY at the v1.30.0 tag).
- Download size: about 9.3 MB gzip before the first move (above). The
  cheapest cut is the fp16-weight file (6.5 MB gzip total, same moves on the
  269 positions) once it has its own ladder rating; after that, a
  reduced-operator onnxruntime wasm build. Neither is done here.
- Phones: network time on a real phone is VERIFY.
