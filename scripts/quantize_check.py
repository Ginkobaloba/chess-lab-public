"""Quantize a checkpoint's ONNX to int8 weights and measure what it costs.

Writes ``<ckpt>.int8.onnx`` next to the checkpoint and a receipt JSON with
both file sizes, validation top-1 move match for fp32 and int8, and the rate
at which the two pick the same legal arg-max move, on the first ``--n``
validation positions of the data set (the same ``g % VAL_EVERY == 0`` split).

Usage:

    python scripts/quantize_check.py --onnx D:/chess-lab-data/runs/<run>/ckpt_<step>.onnx \
        --data D:/chess-lab-data/positions/<name> --out receipts/<name>/quantization.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402

from chesslab import encode, hw  # noqa: E402
from chesslab.data import VAL_EVERY  # noqa: E402
from chesslab.export import quantize_int8  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=50_000)
    args = ap.parse_args()
    q = args.onnx.with_suffix(".int8.onnx")
    q_bytes = quantize_int8(args.onnx, q)
    xs, ys = [], []
    for shard in sorted(args.data.glob("shard_*.npz")):
        d = np.load(shard)
        val = d["g"] % VAL_EVERY == 0
        xs.append(d["x"][val])
        ys.append(d["y"][val])
        if sum(len(y) for y in ys) >= args.n:
            break
    x = np.concatenate(xs)[: args.n]
    y = np.concatenate(ys)[: args.n].astype(np.int64)
    planes = encode.planes_np(x)
    res = {}
    picks = {}
    for tag, path in (("fp32", args.onnx), ("int8", q)):
        sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        logits = np.concatenate([sess.run(["policy"], {"planes": planes[i : i + 4096]})[0]
                                 for i in range(0, len(planes), 4096)])
        picks[tag] = logits.argmax(1)
        res[tag] = {"bytes": path.stat().st_size, "val_top1_unmasked": float((picks[tag] == y).mean())}
    out = {
        "source": str(args.onnx),
        "method": "onnxruntime.quantization.quantize_dynamic, QInt8 weights",
        "val_positions": int(len(y)),
        **res,
        "argmax_agreement": float((picks["fp32"] == picks["int8"]).mean()),
        "note": "top-1 here is over all 4096 logits (unmasked), a slight underestimate of legal-move top-1. "
                "Ladder strength of the int8 file is not measured by this script.",
        "commit": hw.git_commit(),
    }
    assert q_bytes == res["int8"]["bytes"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
