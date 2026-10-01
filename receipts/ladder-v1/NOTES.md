# Notes on ladder-v1 (hand-written; every number here is from RESULTS.md / fit.json)

## What this run is

The council memo's first step, as prescribed: a 6-rung round robin (random,
1-ply material, SF depth 1, SF Skill 0, SF depth 3, SF UCI_Elo 1320), 200
games per pairing, 3000 games, time control A (see `docs/LEDGER.md`).

Provenance: `ladder-config.json` records commit `e64ec8a` with `dirty: true`
because the games were played from the working tree before the ladder code
was committed. That tree became the commit that adds this directory. The only
later change to the code these games ran is the addition of the `material2`
and `mix:` players to `chesslab/players.py`; no code path used by the v1 specs
changed.

## Result: the memo's reversal trigger fired

- Max |cycle residual| is 375 Elo, above the memo's 150 trigger, in the
  random / material1 / sf-d1 triangle.
- Only 1 of 5 adjacent links is in the 20-80% band.
- Prediction misses stay small (max 2.25 points), so the joint fit is not
  internally inconsistent where it has information; the problem is where it
  has none.

Per the memo, the sub-1320 segment of *this* ladder is "relative,
unanchored". The random (419) and material1 (793) numbers are not usable
ratings.

## Why

- **A hole below the pin.** material1 scores 0-1-199 against sf-elo1320 and
  0-1-199 against sf-skill0. There are no informative games between about 800
  and 1320, so the chain has no link there.
- **Draw-driven residuals.** The only unsaturated route from the bottom rungs
  to the pin goes through sf-d1, and the weak side's points there are all
  draws (random 0-12-188, material1 0-18-182), mostly threefold repetitions
  where a deterministic depth-1 search failed to convert. That measures
  sf-d1's conversion habits, not the weak side's play: exactly the style
  intransitivity the Falsifier seat predicted.
- The bootstrap CIs (random 339 to 481) are honest about sampling noise and
  silent about this structural problem.

## Other findings

- **sf-skill0 is the same player as sf-elo1320** (score 0.502 over 200
  games). Expected: Stockfish converts UCI_Elo into an internal skill level,
  and its own FAQ puts Skill 0 at about 1347 at the calibration time control.
  That link carries no information and the rung is dropped from v2.
- **The memo's rung order was wrong above the pin.** SF depth 1 with NNUE fits
  at about 1582 and depth 3 at about 1880, both above 1320. Above the pin the
  chain is 1320 -> sf-d1 -> sf-d3 with links at 0.838 and 0.835, just outside
  the band.

## Follow-up

Ladder v2 fills the gap (mixture rungs, 2-ply material, SF UCI_Elo 1500 and
1700 as calibration checks) and runs the TC B repeat of the 1320 link. Its
receipt is separate so this one stays the record of the prescribed test.
