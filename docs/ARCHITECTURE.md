# Architecture note (council memo, first step 3)

## Board encoding

`chesslab/encode.py`. Side-to-move frame (Black-to-move positions are mirrored).
19 input planes of 8x8: 12 piece planes, 4 castling planes, 1 en-passant
plane, 1 half-move clock plane, 1 constant plane. No move history (Maia-1 uses
8 plies of history; this is a deliberate size and simplicity trade, and a
candidate ablation). Positions are stored as 67-byte compact records and
expanded on the GPU during training (`model.planes_torch`, tested equal to the
NumPy expansion used at inference).

## Network

`chesslab/model.py`. Residual CNN, default 8 blocks x 96 filters, about 1.5M
parameters. Policy head is fully convolutional: 64 output channels, where
channel `to` at square `from` is the logit of `from -> to` (4096 logits, no
dense layer). Queen promotions use the plain from/to index; under-promotions
are not representable (dropped from training, never played). WDL value head
(3 logits) is trained jointly at weight 0.25 so a later search or RL phase can
use it without changing the net shape (the memo's "value-head-capable"
constraint). The ladder player ignores the value head and plays the arg-max
legal move (one node, as Maia).

## Size budget and quantization plan

- fp32 ONNX: about 6.0 MB (measured by `chesslab/train.py` per checkpoint,
  `onnx_bytes` in `metrics.jsonl`).
- int8 weight quantization (`export.quantize_int8`, onnxruntime dynamic
  quantization): measured 1,548,347 bytes for the sup-v1 final checkpoint,
  84.6% arg-max agreement with fp32 (`receipts/sup-v1-ratings/quantization.json`); the strength cost must be
  measured on the ladder before the quantized file is called "the model that
  was rated" (memo reversal trigger).
- onnxruntime-web WASM runtime: the memo's "about 3.5 MB gzipped" estimate is
  replaced by measured numbers (`receipts/web-v1/bundle-size.json`,
  onnxruntime-web 1.30.0, wasm backend only): `ort-wasm-simd-threaded.wasm`
  14,239,897 bytes, 3,687,160 gzip -9, 2,355,011 brotli; the worker script
  (onnxruntime-web JS, chess.js, encoder) 117,469 bytes, 40,143 gzip. Runtime
  plus the rated fp32 model before the first move: 9,313,529 bytes gzip,
  7,914,942 brotli (the model compresses only from 6,014,759 to 5,585,440).
  The int8 file runs in onnxruntime-web but is slower there than fp32 (median
  29.6 ms against 4.4 ms per evaluation, `receipts/web-v1/e2e.json`), so it
  saves download, not compute. An fp16-weight file (`export_web.py --fp16`,
  float16 storage, float32 arithmetic) is 3,016,025 bytes (2,789,104 gzip),
  picks the same top-1 as fp32 on all 269 parity positions at the same speed,
  and is not rated.

## Browser build

`web/` (details in `web/README.md`). The network runs in a Web Worker through
onnxruntime-web (WebAssembly backend, one thread); chess.js generates legal
moves; `web/src/encode.ts` reproduces `chesslab/encode.py` and is held to it
by `receipts/web-v1/encode_golden.json` (same compact bytes, planes hash and
legal indices on 64 positions). The worker plays the legal arg-max, as the
ladder's `net:` player does. `scripts/export_web.py` re-exports the final
checkpoint, which is byte-identical to the rated ONNX file, and checks
PyTorch against ONNX (`receipts/web-v1/parity.json`); the Playwright e2e
checks that the browser picks the same top-1 as Python onnxruntime on all 269
parity positions.

## Rating

`chesslab/ladder.py`, `chesslab/analysis.py`, `scripts/ladder_report.py`,
`scripts/rate_checkpoints.py`. Chained ladder, joint Bradley-Terry fit
(`chesslab/stats.py`, copied from draughts-lab) anchored at Stockfish 19
`UCI_Elo 1320`, stratified bootstrap 95% CIs, cycle residuals and prediction
misses published as receipts.

Label text: "engine-ladder Elo (Stockfish 1320-anchored, time control X), 95%
CI". Below 1320: "extrapolated below 1320 through the ladder chain". Never a
human rating.
