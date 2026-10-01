# HANDOFF -- 2026-09-19 -- phase3

## What this session did

Session Clean_Up (dev-82), chess-lab feature manager, landed the whole phase 1
and 2 stack. Merges were done by the Orchestrator under Drew's merge grant.

- Every PR is on main, rebase-merged in this order:
  #1 scaffold, #2 ladder, #8 one file per ledger entry, #3 data and training,
  #4 TC B receipt, #5 int8 rating, #6 browser build prep, #7 phase-2 handoff,
  #9 fp16 rating.
- #8 moved the ledger to `docs/ledger/` (one file per entry, `scripts/ledger.mjs`)
  and froze `docs/LEDGER.md`. `ledger check` is now a REQUIRED status check on
  main (strict off, enforce_admins on, linear history on).
- Before each layer merged, it was rebased with an explicit fork point. Each
  branch's own diff was checked identical before every force-with-lease push.
- Cleanup: the local checkout is on main at 0/0. Stack branches were deleted
  locally (all patch-equivalent on main) and remotely (delete on merge). There
  are no worktrees and no chess job processes.

## Receipts

On main; see each folder's NOTES.md for commit, seed, hardware and wall time.
All ratings are engine-ladder Elo (Stockfish 19 UCI_Elo 1320-anchored,
time control A unless stated), 95% CI, not a human rating.

- `receipts/tcb/`: the 1M-node 1320 rung fits 1342 (1294 to 1388). This is a
  null drift result at 200 games per pairing, not proof of zero drift.
- `receipts/int8-v1/`: int8 1383 (1348 to 1418) vs fp32 1444 (1411 to 1478).
  The paired difference is -61 (CI -106 to -20). int8 is measurably weaker and
  about 7x slower per evaluation. Do not ship it.
- `receipts/fp16-v1/`: fp16 1434 (1397 to 1469) vs fp32 1444 (1414 to 1477)
  in the joint fit.
  - The paired difference is -10 (CI -56 to +35). That is not proof of
    equality; it rules out fp16 being more than about 56 weaker.
  - fp16 vs int8: +51 (CI +7 to +97).
- `receipts/web-v1/`:
  - Browser vs Python parity is 269/269, and the encoder golden matches
    byte for byte.
  - Measured first-move download: about 9.3 MB gzip with fp32, about 6.5 MB
    with fp16.

## Background jobs

- None running. Checked pid files under `D:\chess-lab-data\arena`
  (tcb, int8-v1, fp16-v1, rate-sup-v1): all have exited.

## What is currently broken or incomplete

- `scripts/ladder_report.py` always prints "time control A" in its label
  (documented in `receipts/tcb/NOTES.md`, not fixed).
- `README.md` still lists `LEDGER.md` without pointing at `docs/ledger/`.
- The Playwright e2e for the web build was not re-run after the restack
  (vitest 139/139 and tsc were). `cpu-cap.ps1` has not been run.
- ONNX Runtime's native `ThirdPartyNotices.txt` is not in the npm package. It
  must be found and shipped before any public page.
- Real-phone browser timing is unmeasured.

## What the next session should do first

1. Nothing public until Drew answers the gates below.
2. Small, ungated cleanups:
   - Fix the TC label in `ladder_report.py`.
   - Point README at `docs/ledger/`.
   - Re-run the web Playwright e2e on main.
3. If Drew approves fp16 as the served file, switch the browser build's
   default model to fp16 and re-verify parity. The ladder rating is already
   receipted.

## Open questions for Drew

- Repo license (GPL-3 for the tooling because it imports python-chess; the
  browser bundle has no GPL code).
- Whether anything below 1320 is ever shown, and its public label.
- Maia-2, even as an offline anchor (recommendation: skip).
- Training data rating band (1800 to 2199 was an agent pick).
- First-move download budget: about 6.5 MB gzip with fp16 (about 9.3 MB with
  fp32). Is that acceptable, or should a reduced-operator ORT build come next?
- Serve fp16 instead of fp32? (Recommended: it halves the model with no
  detectable strength loss at this sample size.)

## Pointers

- Design call: `C:\dev\COUNCIL_CHESS_V2_2026-09-19.md`
- Project CLAUDE.md: `C:\dev\chess-lab\CLAUDE.md`
- Licenses: `docs/LICENSES.md`; decisions: `docs/ledger/` (old `docs/LEDGER.md` frozen)
- Previous handoffs: `docs/handoffs/HANDOFF_2026-09-19_phase1.md`, `..._phase2.md`

## Next Session Onboarding

Future sessions: read `C:\dev\SESSION_PROTOCOL.md`, then `CLAUDE.md` in
this project, then this file, then run `vstart`.
