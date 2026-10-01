# Notes on int8-v1 (hand-written; numbers are from RESULTS.md / fit.json)

## Scope of this receipt

Per `docs/handoffs/HANDOFF_2026-09-19_phase1.md` ("rate the int8 file against
the 3 rungs nearest the final checkpoint"): the int8-quantized export of the
sup-v1 final checkpoint (`D:\chess-lab-data\test\final_fp32.int8.onnx`,
`receipts/sup-v1-ratings/quantization.json`) was rated on the engine ladder,
time control A, against the 3 ladder-v2 rungs nearest the final checkpoint's
published 1445 (1412 to 1478) joint fit: **sf-elo1500** (1468 in the joint
fit), **sf-d1** (1521), and **sf-elo1320** (1320, the anchor) -- distances 23,
76 and 125 Elo. These are the same 3 rungs the final checkpoint itself was
topped up against in `receipts/sup-v1-ratings` (100 games each, stage 2 of
its adaptive protocol), chosen there by the same nearest-3-by-fitted-Elo
rule.

## Rating path already loads a quantized ONNX file; no loader code was needed

`chesslab/players.py`'s `NetPlayer` (spec `net:<path.onnx>`) loads any ONNX
file through `onnxruntime.InferenceSession` and reads/writes float32 tensors
at the graph boundary; the quantization (`onnxruntime.quantization.quantize_dynamic`,
QInt8 weights) only changes internal weight tensors, which onnxruntime
handles transparently. Verified directly before running anything: loading
both `test/final_fp32.onnx` and `test/final_fp32.int8.onnx` through
`NetPlayer` and playing 5 plies from the start position produced legal,
distinct move sequences from both files with no code changes
(`scripts/rate_checkpoints.py`, `chesslab/ladder.py` needed none either).

One measured difference worth recording since `docs/ARCHITECTURE.md` budgets
onnxruntime-web bytes: per-move latency on one CPU thread was about 8x
higher for the int8 file than fp32 in that same 5-ply smoke test (roughly
0.03 s vs 0.004 s per move here). This is a real finding about dynamic
quantization overhead on this small a network, not a game-time concern (a
game is dominated by the Stockfish opponent's search, not the net's forward
pass), and not itself receipted at scale (n=5 plies); flag it for whoever
picks up the onnxruntime-web budget item.

## What changed in the repo

`scripts/ladder_report.py` gained an optional `--diff A B` flag: given two
player names already in the fit, it reports `Elo(A) - Elo(B)` with a 95% CI
from the *same* bootstrap resamples as the joint fit (`EloFit.diff_ci`,
`chesslab/stats.py`, unchanged, copied verbatim from draughts-lab and already
carrying this method). This was the one piece of new code this receipt
needed: nothing upstream computed a paired delta CI between two named
players. Two tests were added in `tests/test_players.py`
(`test_diff_ci_no_gap_ci_contains_zero`, `test_diff_ci_detects_a_real_gap`)
covering a null case (identical records -> CI contains 0) and a known ~100
Elo gap (CI brackets it); the full suite (13 tests) passes.

## Protocol and provenance

- New games: `int8-final` (the int8 file) vs `sf-elo1320`, `sf-elo1500`,
  `sf-d1`, 100 games each (300 total), time control A, same seed formula
  (`derive_seed(run_id, pairing_id, game_index)`) and 100-entry opening book
  as every other ladder receipt. Run id `int8-v1`, `chesslab.ladder` CLI,
  16 workers, wall time 152.9 s, 0 missing, 0 shared-process games
  (`D:\chess-lab-data\arena\int8-v1\ladder-config.json`, copied into this
  directory's games are the 300 new games only -- see below). Commit
  `8ca07e3` at play time; `dirty: true` in that config refers only to the
  then-uncommitted `--diff` addition and its tests, not to any code on the
  game-playing path (`chesslab/ladder.py`, `chesslab/game.py`,
  `chesslab/players.py` were unchanged).
- `receipts/int8-v1/games.jsonl` in this directory holds **only those 300 new
  games**. The joint fit in `fit.json` / `RESULTS.md` (14,580 games, matching
  the published-scale network) also draws on two already-committed receipts,
  reused verbatim with zero replayed games:
  `receipts/ladder-v2/games.jsonl` (9,000 games) and
  `receipts/sup-v1-ratings/games.jsonl` (5,280 games, includes the final
  checkpoint `net@80000` vs these same 3 rungs, 100 games each -- verified
  beforehand that all 100 game indices 0-99 are present for each of the 3
  rungs, so nothing needed replaying). Not re-committing 14,280 already-
  receipted games avoids doubling the repo's data for zero new information;
  to reproduce `fit.json` exactly, concatenate
  `receipts/ladder-v2/games.jsonl` + `receipts/sup-v1-ratings/games.jsonl` +
  `receipts/int8-v1/games.jsonl` (in that order, though order does not affect
  the fit) into one `games.jsonl` and run:
  `python scripts/ladder_report.py --name int8-v1 --arena <that dir> --diff int8-final net@80000`
- Also verified before running: `sha256(D:\chess-lab-data\runs\sup-v1\ckpt_080000.onnx)`
  equals `sha256(D:\chess-lab-data\test\final_fp32.onnx)`, confirming the int8
  file's stated parent (`quantization.json`) is in fact the same final
  checkpoint being compared against here.

## Result

Same joint Bradley-Terry fit as `receipts/sup-v1-ratings` (anchor
sf-elo1320 = 1320), extended with `int8-final`'s 300 games. Label:
engine-ladder Elo (Stockfish 19 UCI_Elo 1320-anchored, time control A), 95%
CI; not a human rating.

| player | Elo | 95% CI |
|---|---|---|
| int8-final | 1383 | 1348 to 1418 |
| net@80000 (fp, final checkpoint) | 1444 | 1411 to 1478 |

`Elo(int8-final) - Elo(net@80000) = -61.0, 95% CI -106.3 to -20.0`
(`EloFit.diff_ci`, paired bootstrap: same resamples used for both players, so
the correlation between their fits is accounted for, not assumed
independent). **The CI excludes 0: int8 is statistically distinguishable
from fp, and weaker by roughly 20 to 106 Elo (point estimate 61).** This is
not the 84.6% argmax-agreement number re-expressed; it is a separate,
game-play-based measurement, and it says the quantization is not free at the
ladder level even though per-position argmax agreement looked high.

fp's Elo here (1444) differs from the previously published 1445 (1412 to
1478) by about 1 point: the fit is joint over all 23 players (10 rungs, 12
checkpoints, int8), so adding int8's 300 games (which touch sf-elo1320,
sf-elo1500 and sf-d1) very slightly moves every other player's MLE estimate
through the shared network. The shift is far inside both CIs' width and is
not a finding.

### Per-rung scores (100 games each; first player's score)

| rung | int8-final | net@80000 (fp) |
|---|---|---|
| sf-elo1320 | 0.570 (48-18-34) | 0.720 (63-18-19) |
| sf-elo1500 | 0.355 (22-27-51) | 0.455 (36-19-45) |
| sf-d1 | 0.355 (8-55-37) | 0.340 (16-36-48) |

int8 scores clearly lower against sf-elo1320 and sf-elo1500 (its main losses
of strength); against sf-d1 the two are close (int8 slightly higher score,
but with far more draws and fewer decisive games), consistent with the
overall ~61 Elo gap being real but modest, and with int8 landing (1383)
between the sup-v1 curve's step 32,000 (1354) and step 48,000 (1425)
checkpoints -- quantization cost this model roughly what the last few
training doublings bought it.

### A caveat on this receipt's own "checks" section

`scripts/ladder_report.py`'s generic route/adjacency analysis ran over the
full 23-player network (10 rungs + 12 checkpoints + int8), which is a much
larger combinatorial space of indirect triangles (708 unsaturated, vs 54 in
`receipts/ladder-v2` alone) than the memo's reversal-trigger check was ever
designed to cover -- most of the large residuals are checkpoint-vs-checkpoint
routes through rungs neither checkpoint played much (an artifact of the
adaptive stage-2 protocol, where each checkpoint only gets deep data against
its own 3 nearest rungs). This is not a new failure of the core ladder: the
memo's actual trigger check is `receipts/ladder-v2`'s own (10 rungs only),
already receipted there, and unchanged by this run (holds at and above 1320,
fails below, as before). Do not quote this receipt's "Max |cycle residual|:
651.3 Elo (FIRED)" as a new problem with the ladder; it reflects the checkpoint
network's known non-transitivity across training stages, not the rung chain.
