# Notes on tcb (TC B time-control check; hand-written; numbers are from RESULTS.md / fit.json)

## What this run is

The memo's TC B drift check: the same Stockfish UCI_Elo 1320 pin used as the
ladder anchor at TC A (`sf-elo1320`, 100k nodes/move) played at 1M nodes/move
instead (`sf-elo1320-1m`, about 1 s/move), 200 games each against
`sf-elo1320` and against `sf-d1`, 400 games total. Run id `tcb-v1`, started
2026-09-19T04:50:14-0500, wall time 2342.3 s, commit `3f84f3e`, hardware and
seed formula in `ladder-config.json`. `tcb.log` (`D:\chess-lab-data\arena\tcb.log`)
ends "ladder: 400 games recorded, 0 missing, shared-process games 0".

Rungs and specs: `chesslab/ladder.py` `RUNGS` (`sf-elo1320-1m` is the
TC B entry, comment: "the same 1320 pin at 1M nodes per move (about 1 s),
for the drift check").

## Label quirk in `fit.json`/`RESULTS.md`

Fixed in PR #11: `ladder_report.py` now names the actual time control(s)
of the players in the fit (`chesslab.ladder.tc_label`), so a rerun of this
report would no longer show this quirk. This receipt's committed
`fit.json`/`RESULTS.md` are historical and were not regenerated; the
paragraph below still describes what they show.

`scripts/ladder_report.py`'s `LABEL` constant always formats
`TC_LABEL["A"]` regardless of which arena it is given, because the anchor
(`sf-elo1320`) is defined and fixed at TC A (100k nodes) in every run,
including this one. So the generated label text literally says "time
control A: Stockfish 19, ... 100k nodes/move" even though this run's whole
purpose is to test the 1M-node ("TC B") version of the pin. That is a known
quirk of the script, not a data error: read the `player` column, not the
`label` field, to know which time control produced each number.
`sf-elo1320` (100k nodes, fixed at 1320) is TC A here exactly as everywhere
else; `sf-elo1320-1m` (1M nodes) is the TC B measurement; `sf-d1` (fixed
depth, no time control) is included as a stable reference point.

## Result: the 1320 pin does not move detectably from 100k to 1M nodes

- **sf-elo1320-1m fits to 1342 (1294 to 1388)** against the TC A anchor
  fixed at 1320. The anchor's value (1320) is inside this 95% CI, so the
  +22 point estimate is not distinguishable from zero at this sample size
  (200 games in the direct pairing).
- Direct head-to-head, `sf-elo1320-1m` vs `sf-elo1320`: score 0.532
  (0.463 to 0.600), W-D-L 104-5-91 over 200 games. A true zero-drift result
  would score 0.500; 0.532 sits well inside the CI around that.
- Direct head-to-head against `sf-d1` (200 games each, same opponent, same
  engine build, same hardware, only the pin's node budget differs):
  - TC A (`sf-elo1320` at 100k nodes, from `receipts/ladder-v2/fit.json`
    pair `sf-elo1320~sf-d1`): score 0.175 (0.129 to 0.234), W-D-L 14-42-144.
  - TC B (`sf-elo1320-1m` at 1M nodes, this run): score 0.168
    (0.122 to 0.225), W-D-L 18-31-151.
  - The two scores and their 95% CIs overlap almost completely (both
    centered near 0.17). No detectable difference from a 10x increase in
    node budget.
- Both memo reversal triggers are silent on this run: only one
  two-pairing chain exists (`sf-elo1320-1m` between the two anchors), so
  there is no triangle for a cycle-residual check (0 unsaturated
  triangles), and the max prediction miss is 0.0 pts. The
  `sf-d1 over sf-elo1320-1m` adjacent link is outside the 20-80% band
  (score 0.833 for sf-d1), which just means that pairing carries less
  information about the boundary between the two, not a data problem.

## Conclusion

At this sample size (200 games per pairing), moving the anchor's node
budget from 100k to 1M nodes per move produces no statistically
detectable rating drift: the 1M-node pin's fitted Elo (1342, CI 1294 to
1388) contains the TC A anchor value (1320), and its score against the
fixed reference `sf-d1` (0.168, CI 0.122 to 0.225) matches the TC A pin's
score against the same opponent (0.175, CI 0.129 to 0.234) within CI. This
is a null result stated plainly, not a confirmed absence of any drift: a
larger sample could still resolve a small effect. See
`receipts/ladder-v2/NOTES.md` for the ladder-wide drift paragraph this
receipt feeds.
