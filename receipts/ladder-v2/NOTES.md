# Notes on ladder-v2 (hand-written; numbers are from RESULTS.md / fit.json)

## What this run is

The gap-filled ladder that follows ladder-v1's fired trigger: 10 rungs, full
round robin, 200 games per pairing, 9000 games, time control A. New rungs:
`m1r50` (50% random, 50% material1 moves), `material2` (2-ply material
minimax), `sf1320m1` (50% material1, 50% SF UCI_Elo 1320 moves), and SF
UCI_Elo 1500 and 1700 as calibration checks. `sf-skill0` was dropped (same
player as the pin, see ladder-v1). Rungs and specs: `chesslab/ladder.py`
`RUNGS`.

Provenance: the run was started three times from the same command and
resumed from `games.jsonl` (the runner skips recorded game ids). Attempts 1
and 2 died on a Stockfish start-up timeout under full CPU load (python-chess's
10 s default, then 120 s, while a 12-worker data extraction, the training job
and other host load were running). Commits `3b8c655` (120 s timeout) and
`3f84f3e` (a failed game is logged and replayed instead of ending the run)
fixed that. No game logic changed between attempts; `ladder-config.json`
records the last commit.

## Result: the trigger still fires, but only below the pin

- All 54 unsaturated triangles: max |cycle residual| 475 Elo; max prediction
  miss 10.6 points outside the observed CI. Both memo triggers fire.
- **Stockfish-only triangles** (sf-elo1320, sf-elo1500, sf-elo1700, sf-d1,
  sf-d3; 21 routes): max |residual| 101 Elo, under the 150 trigger. Every
  adjacent link at and above the pin is in the 20-80% band except
  sf-d3 over sf-elo1700 (0.815).
- Below the pin, the large residuals come from style intransitivity: the
  mixture rung `sf1320m1` against `material2` and the pin (379), and sf-d1's
  repetition draws against weak players. `material2` over `sf1320m1` scores
  0.927 while the pin over `material2` scores 0.958, which a single Elo line
  cannot reproduce.

So: **at and above 1320 the chain holds at the memo's threshold; below 1320
it does not, and the memo's rule applies: that segment is "relative,
unanchored".** The sub-1320 values also move by hundreds of Elo depending on
which games enter the fit (random is 171 here, 419 in ladder-v1, 470 in the
joint fit with checkpoints), which the bootstrap CIs do not show.

## Calibration drift at TC A (UCI_Elo nominal vs fitted)

- sf-elo1500: fitted 1465 (1438 to 1492), nominal 1500.
- sf-elo1700: fitted 1612 (1582 to 1638), nominal 1700.

Measured: the nominal 380-Elo spread from UCI_Elo 1320 to 1700 fits as 292
at TC A in this ladder. This does not say why; TC B (the pin at 1M nodes per
move) is the receipt that speaks to time control, and it is separate.

## TC B result (2026-09-19): no detectable drift from 100k to 1M nodes

`receipts/tcb/` (run id `tcb-v1`, 400 games) put the same UCI_Elo 1320 pin
at 1M nodes/move (`sf-elo1320-1m`, "engine-ladder Elo (Stockfish 19
UCI_Elo 1320-anchored, time control B: Stockfish 19, 1 thread, 1M
nodes/move for the UCI_Elo 1320 rung), 95% CI") on the board against the
TC A anchor (`sf-elo1320`, 100k nodes, fixed at 1320) and against `sf-d1`.
Result: **sf-elo1320-1m fits to 1342 (1294 to 1388)**, and the anchor's
value (1320) lies inside that CI, so the +22 point estimate is not
distinguishable from zero at this sample size. Direct score against
`sf-d1` also matches across time controls: 0.175 (0.129 to 0.234) at TC A
(this ladder's `sf-elo1320~sf-d1` pair, above) vs 0.168 (0.122 to 0.225)
at TC B, fully overlapping CIs. Stated plainly: this is a null result, not
proof of zero drift; it is inconclusive at anything smaller than the
observed effect size, and a larger sample would be needed to rule out a
small time-control sensitivity. Full numbers, terminations and the
adjacent-link/route checks are in `receipts/tcb/RESULTS.md` and
`receipts/tcb/NOTES.md`.
