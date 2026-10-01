# Notes on fp16-v1 (hand-written; numbers are from RESULTS.md / fit.json)

## Scope of this receipt

Same protocol as `receipts/int8-v1` (see that NOTES.md), applied to the other
export in `scripts/export_web.py --fp16`: weights stored as float16 with a
Cast back to float32 at load, so the arithmetic itself stays float32
(`receipts/web-v1/parity.json`'s `fp16_weights`). The fp16-weight export of
the sup-v1 final checkpoint
(`D:\chess-lab-data\export\sup-v1-final.fp16w.onnx`) was rated on the engine
ladder, time control A, against the same 3 rungs int8 was rated against:
**sf-elo1320** (the anchor), **sf-elo1500**, **sf-d1** (100 games each) --
chosen there by the nearest-3-by-fitted-Elo rule against the final
checkpoint's published Elo, and reused here so `fp16-final`, `int8-final` and
`net@80000` all sit on the same 3 pairings for a clean 3-way comparison.

## No loader or code changes needed for the fp16 file either

`NetPlayer` (`chesslab/players.py`) loads any ONNX file through
`onnxruntime.InferenceSession`; the fp16-weight file adds only `Cast` nodes at
the graph boundary of each initializer, which onnxruntime folds into the
constant weights at session load (the arithmetic dtype the session actually
runs is unaffected). Verified directly before running anything: loading both
`export/sup-v1-final.onnx` (fp32) and `export/sup-v1-final.fp16w.onnx`
through `NetPlayer` and playing 5 plies from the start position from the
worktree at `f1811de` produced byte-for-byte identical move sequences
(`e2e4 e7e5 g1f3 b8c6 f1c4` for both), consistent with `receipts/web-v1`'s
269/269 top-1 agreement and a much smaller max policy-logit difference
(0.0465) than int8's (13.9).

## What changed in the repo

`scripts/ladder_report.py --diff A B` (added by `receipts/int8-v1`) is now
`--diff A B` repeatable (`action="append"`): this receipt needed two named
diffs in one fit (fp16 vs fp32, fp16 vs int8) computed from the *same*
bootstrap resamples as each other and as the joint fit, which the previous
single-pair `--diff` could not do without refitting (and thus using different
resamples for each pair, only usable by rerunning the whole script twice with
a different seed each time -- unnecessary, and the resample seed is fixed at
0 by design). `fit.json` gained a `"diffs"` list (the old singular `"diff"`
key is kept, `None` when more than one `--diff` is passed, unchanged when
exactly one is, so `receipts/int8-v1/fit.json`'s shape is not being changed
retroactively). `RESULTS.md` now prints one "Named pair difference" section
per `--diff`. No changes to `chesslab/stats.py`'s `EloFit.diff_ci` (unchanged
from int8-v1) or to the existing `tests/test_players.py` diff_ci tests, which
still cover the method itself; the full suite (13 tests) still passes
unchanged. The CLI's new repeatable behavior was smoke-tested against the
already-committed `receipts/ladder-v2/games.jsonl` (two arbitrary named
pairs, `sf-elo1500`/`sf-d1` and `sf-elo1320`/`sf-d3`) before the real run, in
a throwaway `receipts/_smoke_multidiff` output directory that was deleted
afterward and was never committed.

## Protocol and provenance

- New games: `fp16-final` (the fp16-weight file) vs `sf-elo1320`,
  `sf-elo1500`, `sf-d1`, 100 games each (300 total), time control A, same
  seed formula (`derive_seed(run_id, pairing_id, game_index)`) and 100-entry
  opening book as every other ladder receipt. Run id `fp16-v1`,
  `chesslab.ladder` CLI, 16 workers, wall time 147.4 s, 0 missing, 0
  shared-process games (`D:\chess-lab-data\arena\fp16-v1\ladder-config.json`,
  copied verbatim into this directory as `ladder-config.json`; this
  directory's `games.jsonl` holds only those 300 new games -- see below).
  Commit `f1811de` at play time, **not dirty** (unlike int8-v1's run, which
  was dirty from the then-uncommitted `--diff` addition and its tests: this
  time the ladder job was launched first, from the clean worktree checked
  out at `feat/int8-rating`'s tip, before `--diff` was made repeatable, so
  the arena's own recorded commit is clean and its wall time is committed
  here rather than living only in prose).
  The seed formula is the *same formula*, not the same seed values: with
  `run_id="fp16-v1"` the derived seeds differ from `int8-v1`'s and from
  `net@80000`'s own games, exactly as int8-v1's differed from
  `sup-v1-ratings`. "Paired" in the diff below refers to the bootstrap
  resamples being shared between the two players being compared, not to the
  three players having played identical games.
- `receipts/fp16-v1/games.jsonl` in this directory holds **only those 300 new
  games**. The joint fit in `fit.json` / `RESULTS.md` (14,880 games) also
  draws on three already-committed receipts, reused verbatim with zero
  replayed games: `receipts/ladder-v2/games.jsonl` (9,000 games),
  `receipts/sup-v1-ratings/games.jsonl` (5,280 games) and
  `receipts/int8-v1/games.jsonl` (300 games). Not re-committing 14,580
  already-receipted games avoids doubling the repo's data for zero new
  information; to reproduce `fit.json` exactly, concatenate
  `receipts/ladder-v2/games.jsonl` + `receipts/sup-v1-ratings/games.jsonl` +
  `receipts/int8-v1/games.jsonl` + `receipts/fp16-v1/games.jsonl` (in that
  order, though order does not affect the fit) into one `games.jsonl` and
  run:
  `python scripts/ladder_report.py --name fp16-v1 --arena <that dir> --diff fp16-final net@80000 --diff fp16-final int8-final`
  `fit-sources.json` in this directory is the hand-written concatenation
  note (source list, source paths, total game count, commit, hardware) that
  was actually copied into the fit-arena directory to build `fit.json`;
  `ladder-config.json` is the real arena config for the 300 new games (the
  one with `wall_s`, `started`, `commit`). This is the one improvement over
  `receipts/int8-v1`, which only committed the concatenation note and left
  its own arena's wall time (152.9 s) recorded in NOTES.md prose only.
- Also verified before running: `sha256(D:\chess-lab-data\export\sup-v1-final.fp16w.onnx)`
  equals `receipts/web-v1/parity.json`'s recorded `fp16_weights.sha256`
  (`0c4382a2b21f98d55d69d47540ee47c63766baaaf4b8487811b6f04a16456304`,
  3,016,025 bytes, matching the task's stated size), and
  `sha256(D:\chess-lab-data\export\sup-v1-final.onnx)` equals both
  `receipts/web-v1/parity.json`'s recorded `rated_onnx.sha256`
  (`b45c625b6e5fea57c8d43610ec9e5d8b34ecb0246e8a77296ca238d547d153b6`) and
  `sha256(D:\chess-lab-data\runs\sup-v1\ckpt_080000.onnx)` (`net@80000`, the
  fp32 file the ladder rated), confirming the fp16 file's stated fp32 parent.
  Export command and provenance for both files (`receipts/web-v1/parity.json`,
  commit `707e165`, not dirty): `python scripts/export_web.py --ckpt
  D:/chess-lab-data/runs/sup-v1/ckpt_080000.pt --int8 --fp16 --receipt
  receipts/web-v1/parity.json` (wall time 8.8 s, hardware: 13th Gen Intel
  i9-13900KF, RTX 4090, Windows 11, Python 3.13.3, torch 2.11.0+cu128, onnx
  1.23.0, onnxruntime 1.30.0). The fp16 and fp32 files already existed on
  disk from that PR's run; nothing was regenerated for this receipt.

## Result

Same joint Bradley-Terry fit as `receipts/int8-v1` (anchor sf-elo1320 =
1320), extended with `fp16-final`'s 300 games. Label: engine-ladder Elo
(Stockfish 19 UCI_Elo 1320-anchored, time control A), 95% CI; not a human
rating.

| player | Elo | 95% CI |
|---|---|---|
| int8-final | 1383 | 1345 to 1419 |
| fp16-final | 1434 | 1397 to 1469 |
| net@80000 (fp32, final checkpoint) | 1444 | 1414 to 1477 |

`Elo(fp16-final) - Elo(net@80000) = -9.6, 95% CI -56.4 to 34.7`
`Elo(fp16-final) - Elo(int8-final) = 51.4, 95% CI 7.3 to 96.6`
(`EloFit.diff_ci`, paired bootstrap: same resamples used for every player in
both comparisons, so the correlation between the three fits is accounted
for, not assumed independent.)

**fp16 vs fp32: the CI contains 0. This is not proof that fp16 and fp32 are
equally strong.** At n=300 games (100 per rung) and this bootstrap, the CI
rules out fp16 being weaker than fp32 by more than about 56 Elo, or stronger
by more than about 35 Elo, at 95% confidence. An effect inside that roughly
90-Elo-wide band would not be detected at this sample size; more games would
narrow it, the same way int8's 300 games were what made *its* ~61 Elo gap
detectable in the first place. Given that fp16-weight storage only rounds
each weight to its nearest float16 value before casting back (not the int8
quantization scheme, which changes the effective computation), a small
undetectable effect is the more likely explanation for the CI containing 0
than a truly larger, hidden effect -- but this receipt cannot distinguish
those from 300 games alone, and does not claim to.

**fp16 vs int8: the CI excludes 0.** fp16 is statistically distinguishable
from, and stronger than, int8 by roughly 7 to 97 Elo (point estimate 51).
This is consistent with int8's own diff-vs-fp32 result (-61.0, 95% CI -106.3
to -20.0, `receipts/int8-v1/NOTES.md`): if fp16 is close to fp32 in strength
and int8 is a real ~61 Elo below fp32, then fp16 minus int8 landing around
+51 Elo (point estimate) is the expected shape, not a new, independent
finding.

### Per-rung scores (100 games each; first player's score)

| rung | fp16-final | int8-final | net@80000 (fp32) |
|---|---|---|---|
| sf-elo1320 | 0.670 (61-12-27) | 0.570 (48-18-34) | 0.720 (63-18-19) |
| sf-elo1500 | 0.470 (37-20-43) | 0.355 (22-27-51) | 0.455 (36-19-45) |
| sf-d1 | 0.350 (16-38-46) | 0.355 (8-55-37) | 0.340 (16-36-48) |

fp16 scores between int8 and fp32 against sf-elo1320 and sf-elo1500 (its
clearest rungs), and is essentially tied with both against sf-d1, where all
three networks draw heavily against depth-1 search. Nothing here contradicts
the joint fit's Elo ordering (int8 < fp16 approx= fp32).

### A caveat on this receipt's own "checks" section (same caveat as int8-v1)

`scripts/ladder_report.py`'s generic route/adjacency analysis ran over the
full 24-player network (10 rungs + 12 checkpoints + int8 + fp16), an even
larger combinatorial space (717 unsaturated triangles, vs 708 in
`receipts/int8-v1` and 54 in `receipts/ladder-v2` alone) than the memo's
reversal-trigger check was designed to cover, for the same reason as
before: most large residuals are checkpoint-vs-checkpoint or
checkpoint-vs-{int8,fp16} routes through rungs neither played much (an
artifact of the adaptive stage-2 protocol). This is not a new failure of the
core ladder; the memo's actual trigger check is `receipts/ladder-v2`'s own
(10 rungs only), already receipted there and unchanged by this run. Do not
quote this receipt's "Max |cycle residual|: 651.3 Elo (FIRED)" or "Max
prediction miss ... 15.26 pts (FIRED)" as new problems with the ladder; they
reflect the checkpoint network's known non-transitivity across training
stages (same 651.3 Elo max residual as `receipts/int8-v1`, since the same
worst triangle apparently does not involve fp16-final), not the rung chain.
