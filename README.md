# chess-lab

Paradigm's chess ML lab: a Maia-style supervised policy (+ value
head) trained on the CC0 Lichess database, rated on a chained engine ladder
anchored at Stockfish 19 `UCI_Elo 1320`, with 95% confidence intervals.
The design follows option 3 of an internal design memo (not included here);
"the memo" below refers to it.

Every number below is copied from a receipt under `receipts/`, which is
produced by a script from recorded games or training logs.

## Phase 1 results

**Rating label:** engine-ladder Elo (Stockfish 19 UCI_Elo 1320-anchored, time
control A: 100k nodes per move for the strength-limited Stockfish rungs), 95%
CI. Not a human rating.

- Final network (step 80,000, 1.5M parameters, 6.0 MB fp32 ONNX, 1.5 MB int8):
  **1445 (1412 to 1478)** in the joint fit; **1483 (1447 to 1521)** against
  the Stockfish rungs only; **1486 (1443 to 1531)** against the three UCI_Elo
  rungs only. The spread between fits (about 40) is systematic error outside
  the CIs. Validation move-match with human moves:
  0.512. (`receipts/sup-v1-ratings*/`)
- Rating vs training steps: `receipts/sup-v1-ratings/RESULTS.md` and
  `curve.png`. The curve crosses 1320 around step 16,000 (1327, 1295 to 1360).
  Earlier checkpoints fit below 1320; those values are extrapolated **and**
  the sub-1320 chain fails the memo's route test (below), so they are
  relative and unanchored.
- Ladder validation (memo first step 1): the prescribed 6-rung round robin
  fired the memo's 150-Elo cycle-residual trigger (375). A gap-filled 10-rung
  ladder holds at and above the pin (max Stockfish-only residual 101) but
  still fails below it (475). (`receipts/ladder-v1/`, `receipts/ladder-v2/`,
  each with a NOTES.md.)
- Licenses: `docs/LICENSES.md`. No Maia weights are used anywhere.

## Layout

- `chesslab/`: encoding, players, games, ladder runner, statistics, chain
  checks, data extraction, model, training, ONNX export.
- `scripts/`: receipt generators (`ladder_report.py`, `rate_checkpoints.py`,
  `quantize_check.py`, `export_web.py`, `gen_encode_golden.py`).
- `web/`: browser build prep (onnxruntime-web in a Web Worker, chess.js,
  encoder golden, local dev page); see `web/README.md`. No public page.
- `receipts/`: game records, configs, fits and notes. Data, checkpoints and
  binaries live under `D:\chess-lab-data`, never in git.
- `docs/`: `ARCHITECTURE.md`, `LICENSES.md`, `ledger/` (decisions and hard
  calls, one file per entry, `node scripts/ledger.mjs new "<title>"`;
  `docs/LEDGER.md` is frozen history, never appended to), `handoffs/`.

## Reproduce

```powershell
uv sync --extra train
$env:PYTHONPATH = "."
# Stockfish 19 official release binary at D:\chess-lab-data\bin (see docs/LICENSES.md for hashes)
.venv\Scripts\python.exe -m chesslab.ladder --out D:\chess-lab-data\arena\ladder-v2 --run-id ladder-v2 `
  --player random --player m1r50 --player material1 --player material2 --player sf1320m1 `
  --player sf-elo1320 --player sf-elo1500 --player sf-elo1700 --player sf-d1 --player sf-d3 --games 200
.venv\Scripts\python.exe -m chesslab.data --src <prefix .pgn.zst> --out D:\chess-lab-data\positions\<name>
.venv\Scripts\python.exe -m chesslab.train --data D:\chess-lab-data\positions\<name> --run D:\chess-lab-data\runs\<run> --steps 80000
.venv\Scripts\python.exe scripts\rate_checkpoints.py --run D:\chess-lab-data\runs\<run> --arena D:\chess-lab-data\arena\<rate> `
  --ladder D:\chess-lab-data\arena\ladder-v2 --name <receipt> --games 20 --adaptive 100 --near 3 --rungs <the ten rungs>
```

Stockfish rungs with a strength limit are not deterministic (Stockfish seeds
its weak-move choice from time), so a rerun reproduces the statistics, not the
exact games. The recorded games are the receipt.

## License

GPL-3.0 (see `LICENSE`). Third-party components and their licenses are
listed in `docs/LICENSES.md`. Stockfish and the Lichess data are not in this
repo.
