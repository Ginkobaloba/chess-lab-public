# HANDOFF -- 2026-09-19 -- phase2

## What this session did

Session Clean_Up (dev-82) took over chess-lab as feature manager from the
Orchestrator after the phase-1 agent ended. Everything below is on stacked PRs
off `feat/train` (#3); nothing is merged. Merge order stays bottom-up:
#1 -> #2 -> #3, then the siblings #4, #5, #6 and this hand-off (#7); the fp16 rating PR (number assigned when opened) stacks on #5.

- **PR #4, TC B receipt:** the 1M-node Stockfish UCI_Elo 1320 rung fits
  1342 (1294 to 1388). This is engine-ladder Elo (Stockfish 19 UCI_Elo
  1320-anchored, time control B for that rung), 95% CI, not a human rating.
  The anchor's fixed 1320 sits inside the CI, so this is a null result at
  200 games per pairing, not proof of zero drift. Scores against sf-d1 are
  also indistinguishable between the two time controls (0.175 vs 0.168). The
  drift paragraph was added to `receipts/ladder-v2/NOTES.md`.
  - Script quirk: `scripts/ladder_report.py` always prints "time control A"
    in its label, because the anchor is fixed at TC A. This is documented in
    `receipts/tcb/NOTES.md`.
- **PR #5, int8 rating:** int8 rates 1383 (1348 to 1418) and fp32 final
  rates 1444 (1411 to 1478) in the same joint fit (engine-ladder Elo, TC A,
  95% CI).
  - The paired difference is -61, CI -106 to -20. It excludes 0, so int8 is
    measurably weaker; the 84.6% arg-max agreement hid this.
  - int8 is also about 7x slower per evaluation than fp32 in onnxruntime (CPU
    and web).
  - Adds `ladder_report.py --diff A B` (paired bootstrap CI), with tests.
- **PR #6, browser build prep:** an ONNX export whose re-export is
  byte-identical to the rated file, plus a TypeScript Web Worker on
  onnxruntime-web (draughts-lab pattern, with provenance headers) and a dev
  page (no public copy).
  - Parity: the browser picks the same top-1 as Python on 269/269 positions.
  - The encoder golden matches byte for byte across Python and TypeScript.
  - Measured download: about 9.3 MB gzip before the first move with fp32
    (ORT wasm 3.69 MB + model 5.59 MB gzip). `docs/ARCHITECTURE.md` is
    corrected.
  - An fp16 export (3.0 MB) agrees on top-1 with fp32 269/269 at the same
    speed, but is UNRATED.
  - Licenses: chess.js BSD-2, onnxruntime-web MIT, no GPL in the browser
    bundle.
- **fp16 rating:** running at hand-off (see Background jobs). Expected as a
  PR stacked on #5.

## Receipts

- `receipts/tcb/` (PR #4): games, ladder-config, fit, RESULTS, NOTES.
- `receipts/int8-v1/` (PR #5): 300 new games, config, fit, RESULTS, NOTES,
  reproduce command.
- `receipts/web-v1/` (PR #6): parity.json, encode_golden.json, e2e.json,
  bundle-size.json.

## Background jobs

- fp16 ladder rating: run id `fp16-v1`, logs under
  `D:\chess-lab-data\arena\fp16-v1*`. Launched by the session's agent; check
  the log and whether the PR exists before relaunching.
- None else. TC B (`tcb-v1`) finished 2026-09-19 05:29 (400/400 games).

## What is currently broken or incomplete

- #4, #5 and #6 each append to the single `docs/LEDGER.md`. The second and
  third to merge will conflict on that file and need a trivial rebase.
  Consider moving chess-lab to the one-file-per-entry ledger
  (`docs/ledger/`, `scripts/ledger.mjs`, as in paradigm-skills #4) to end this.
- `ladder_report.py` label always says TC A (documented, not fixed).
- ONNX Runtime's native `ThirdPartyNotices.txt` is not in the npm package. It
  must be checked and shipped before any public release.
- Real-phone browser timing is unmeasured; `cpu-cap.ps1` was copied but not run.

## What the next session should do first

1. Check the fp16 rating result and its PR. If fp16 is indistinguishable from
   fp32 at a useful effect size, propose serving fp16 (about 2.8 MB gzip saved).
2. After Drew merges #1 to #3, rebase #4, #5 and #6 in merge order,
   resolving the `docs/LEDGER.md` appends.
3. Do nothing public (no /lab/chess page, no rating copy) until Drew answers
   the label questions below.

## Open questions for Drew

- Repo license (GPL-3 for the tooling because it imports python-chess; the
  browser bundle itself has no GPL code).
- Whether anything below 1320 is ever shown, and its public label.
- Maia-2, even as an offline anchor (recommendation: skip).
- Training data rating band (1800 to 2199 was an agent pick).
- Download budget: about 9.3 MB gzip before the first move with fp32, about
  6.5 MB with fp16. Is that acceptable, or should the next step be a
  reduced-operator ORT build?
- Goldens under `receipts/web-v1/` vs a separate `golden/` folder like
  draughts-lab.

## Pointers

- Design call: `C:\dev\COUNCIL_CHESS_V2_2026-09-19.md`
- Project CLAUDE.md: `C:\dev\chess-lab\CLAUDE.md`
- Licenses: `docs/LICENSES.md`; decisions: `docs/LEDGER.md`
- Previous handoff: `docs/handoffs/HANDOFF_2026-09-19_phase1.md`
- Workspace ledger: `C:\dev\LEDGER.md`

## Next Session Onboarding

Future sessions: read `C:\dev\SESSION_PROTOCOL.md`, then `CLAUDE.md` in
this project, then this file, then run `vstart`.
