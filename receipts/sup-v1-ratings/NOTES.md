# Notes on sup-v1 ratings (hand-written; numbers are from RESULTS.md, curve.json, metrics.jsonl, quantization.json)

## What was trained

- Data: `receipts/data/manifest.json`. A 4 GiB byte prefix of the Lichess
  2026-08 standard rated export (CC0), downloaded as HTTP byte ranges and
  concatenated (`download-assembly.txt`), SHA-256 in the manifest. 13,084,145
  games seen, 1,608,168 kept (Blitz/Rapid/Classical, both players 1800 to
  2199, normal or time-forfeit endings), 105,607,106 training and 2,153,874
  validation positions (every 50th game held out), 0 parse errors.
- Net: 8 residual blocks x 96 filters, policy (4096 from-to) + WDL value
  head, 6,014,759-byte fp32 ONNX (`chesslab/model.py`).
- Run: `train-config.json`. 80,000 steps x 2048 = 163.8M samples (about 1.55
  epochs), AdamW, cosine schedule, bf16 autocast, on the RTX 4090, 1,975 s
  wall. Commit `3b8c655`, clean tree.
- Validation move-match (top-1 against the human move, 500k held-out
  positions): 0.512 at the final step, still rising slowly
  (0.503 / 0.509 / 0.512 at 48k / 64k / 80k). No overfitting signal, so the
  final checkpoint is also the validation-best one.
- GPU use (`gpu.log`, nvidia-smi every 30 s): peak 94% utilization, 13,380 MiB
  of 24,564 MiB memory (about 2,500 MiB of it was in use before training),
  64 C, 346.8 W of a 450 W limit.

## How it was rated

- Each checkpoint's ONNX file played through onnxruntime on CPU, arg-max
  legal move, no search. Stage 1: 20 games against each of the 10 ladder-v2
  rungs. Stage 2: topped up to 100 games against the 3 rungs nearest its
  stage-1 fit. 5,280 games, 440 per checkpoint, 0 games sharing a process.
- The rating pool hung with 4 stage-2 games unplayed (two pairings, worker
  processes lost); those 4 were replayed with the same seeds through the
  hardened runner (commit `3f84f3e`). The games were played from commit
  `b744247`; the fit in this directory was produced at `04b8751`.
- One joint Bradley-Terry fit over ladder-v2 (9000 games) plus these 5,280,
  anchored at sf-elo1320 = 1320, bootstrap 95% CIs (1000 resamples).

## Result (label: engine-ladder Elo, Stockfish 19 UCI_Elo 1320-anchored, time control A, 95% CI; not a human rating)

| step | Elo | 95% CI |
|---|---|---|
| 16,000 | 1327 | 1295 to 1360 |
| 32,000 | 1354 | 1319 to 1387 |
| 48,000 | 1426 | 1391 to 1458 |
| 64,000 | 1434 | 1400 to 1467 |
| 80,000 (final) | 1445 | 1412 to 1478 |

Checkpoints before step 16,000 fit below 1320 (531 at step 0 up to 1224 at
step 8,000). **Those values are extrapolated, and ladder-v2 shows the
sub-1320 chain fails the memo's route test, so they are relative and
unanchored.** They show the ordering (the curve rises monotonically) but are
not ratings on any named scale.

## Systematic uncertainty the CIs do not cover

- **Rung-set sensitivity.** Refitting the checkpoints at or above step 16,000
  against the Stockfish rungs only (`receipts/sup-v1-ratings-sf-only/`) moves
  the final checkpoint to 1483 (1447 to 1521); against the three UCI_Elo
  rungs only (1320, 1500, 1700: same engine, same TC, one strength knob;
  `receipts/sup-v1-ratings-ucielo-only/`) it is 1486 (1443 to 1531). The
  spread of the three fits at the final step is 1445 to 1486, about 40 Elo,
  and the two Stockfish-only fits agree, so the joint fit is pulled down by
  the material and mixture rungs. Treat about 40 Elo as a floor on the
  systematic error at the top of the curve.
- **Scale drift at TC A.** In ladder-v2 the UCI_Elo 1500 and 1700 rungs fit
  35 and 88 below nominal (ladder-v2 NOTES); the cause is not established.
  The anchor is Stockfish's 1320 at 100k nodes per move, not at its 120s+1s
  calibration time control.
- **Opponent pool.** Every opponent is Stockfish or a scripted player. Nothing
  here says how the net plays against people.

## Quantization (`quantization.json`)

int8 dynamic weight quantization of the final checkpoint: 1,548,347 bytes
(from 6,014,759). On 50,000 validation positions the int8 file picks the same
move as fp32 84.6% of the time; unmasked top-1 drops from 0.508 to 0.497. The
int8 file has **not** been rated on the ladder, so it is not yet "the model
that was rated" (memo reversal trigger); that is next-phase work.
