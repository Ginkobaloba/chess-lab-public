# HANDOFF -- 2026-09-19 -- phase1

## What this session did

- Created private repo `Ginkobaloba/chess-lab` (`delete_branch_on_merge` on at
  creation). Three stacked PRs, none merged: #1 scaffold + license check,
  #2 ladder + memo step-1 round robin, #3 data + training + ratings.
- License check (`docs/LICENSES.md`): python-chess GPL-3.0+, Stockfish 19
  GPL-3 as an external binary only, Lichess standard DB CC0, Maia-1 GPL-3,
  Maia-2 code MIT with unverified weight terms. No Maia weights used.
- Ladder v1 (memo's 6-rung round robin, 3000 games): trigger fired.
  Ladder v2 (10 rungs, 9000 games): holds at and above 1320, fails below.
- Data: 4 GiB prefix of Lichess 2026-08, 1.61M games, 105.6M training
  positions, under `D:\chess-lab-data\positions\2026-08-p4g-1800-2199`.
- Trained sup-v1 on the RTX 4090 (80k steps, 33 min, 0.512 val move-match),
  12 checkpoints, all rated: final 1445 (1412 to 1478) joint fit, 1483
  (1447 to 1521) Stockfish-rungs-only fit.

## Receipts

- `receipts/ladder-v1/`, `receipts/ladder-v2/` (games, configs, fit, RESULTS, NOTES)
- `receipts/data/manifest.json`, `download-assembly.txt`
- `receipts/sup-v1-ratings/` (games, train config, metrics, curve, gpu.log, quantization, NOTES)
- `receipts/sup-v1-ratings-sf-only/` (sensitivity fit)

## Background jobs

- **TC B run still going at hand-off**: `chesslab.ladder` with run id
  `tcb-v1`, launcher PID in `D:\chess-lab-data\arena\tcb.pid`, log
  `D:\chess-lab-data\arena\tcb.log`, games `D:\chess-lab-data\arena\tcb\games.jsonl`.
  400 games (sf-elo1320 at 1M nodes vs sf-elo1320 and vs sf-d1). It is
  resumable: rerun the same command (in the PR #3 description) if it dies.
  When done: `python scripts/ladder_report.py --name tcb --arena D:\chess-lab-data\arena\tcb`
  (the anchor stays sf-elo1320 at TC A) and commit `receipts/tcb/`.

## What is currently broken or incomplete

- TC B receipt not yet written (job running, see above).
- int8 model not rated on the ladder (84.6% arg-max agreement only).
- `docs/ARCHITECTURE.md` budgets ~3.5 MB for onnxruntime-web: unverified.

## What the next session should do first

1. Finish the TC B receipt and add its drift number to the ladder-v2 NOTES.
2. Rate the int8 file against the 3 rungs nearest the final checkpoint.
3. Wait for Drew's calls below before any public copy or browser work.

## Open questions for Drew

- Repo license (GPL-3 for the tooling, because it imports python-chess).
- Public label for anything below 1320 (the route test failed there).
- Whether Maia-2 is ever used even as an offline anchor.
- Rating band of the training data (1800 to 2199 was an agent pick).

## Pointers

- Design call: `C:\dev\COUNCIL_CHESS_V2_2026-09-19.md`
- Project CLAUDE.md: `C:\dev\chess-lab\CLAUDE.md`
- Licenses: `docs/LICENSES.md`; decisions: `docs/LEDGER.md`

## Next Session Onboarding

Future sessions: read `C:\dev\SESSION_PROTOCOL.md`, then `CLAUDE.md` in
this project, then this file, then run `vstart`.
