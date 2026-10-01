"""Export a checkpoint for the browser build and check ONNX against PyTorch.

Writes, under ``--out`` (default ``D:/chess-lab-data/export``, never in git):

- ``<name>.onnx``: the checkpoint re-exported with ``chesslab.export.export_onnx``
  (the same function, opset and input encoding that produced the rated file);
- ``<name>.int8.onnx`` with ``--int8``: int8 weight quantization of that file
  (``chesslab.export.quantize_int8``). It is NOT the rated model;
- ``<name>.fp16w.onnx`` with ``--fp16``: the same graph with its float
  weights stored as float16, each followed by a Cast back to float32, so the
  arithmetic stays float32 (onnxruntime folds the casts at load). It halves
  the download; it is NOT the rated model;
- ``manifest.json``: ``chess-lab/web-model/v1``, the files the browser worker
  loads, each with bytes and sha256 (the worker checks both before use).

Parity: on ``--n`` seeded positions (``chesslab.webref.seeded_positions``)
plus the hand-picked edge positions that have legal moves, the PyTorch model
(fp32, CPU, eval mode) and each fp32 ONNX file (the re-export and the rated
``ckpt_*.onnx`` next to the checkpoint) must agree: every policy and WDL logit
within ``--atol``, and the same legal arg-max move wherever the best two legal
logits are further apart than ``2 * atol``. The int8 and fp16-weight files
are reported as agreement only (they are expected to differ). The receipt goes to ``--receipt``
and lists, per position, the rated file's top-1 move and logit so the browser
e2e can check that onnxruntime-web picks the same move.

Usage:

    python scripts/export_web.py --ckpt D:/chess-lab-data/runs/sup-v1/ckpt_080000.pt --int8 \
        --receipt receipts/web-v1/parity.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chess  # noqa: E402
import numpy as np  # noqa: E402
import onnx  # noqa: E402
import onnxruntime as ort  # noqa: E402
import torch  # noqa: E402

from chesslab import encode, hw, webref  # noqa: E402
from chesslab.export import export_onnx, quantize_int8  # noqa: E402
from chesslab.model import Net  # noqa: E402

MANIFEST_SCHEMA = "chess-lab/web-model/v1"


def fp16_weights(src: Path, dst: Path) -> int:
    """Store every float32 initializer as float16 plus a Cast to float32 (compute stays float32)."""
    from onnx import TensorProto, helper, numpy_helper

    m = onnx.load(str(src))
    g = m.graph
    keep, casts = [], []
    for init in g.initializer:
        if init.data_type != TensorProto.FLOAT:
            keep.append(init)
            continue
        half = numpy_helper.from_array(numpy_helper.to_array(init).astype(np.float16), f"{init.name}__fp16")
        keep.append(half)
        casts.append(helper.make_node("Cast", [half.name], [init.name], to=TensorProto.FLOAT, name=f"{init.name}__cast"))
    del g.initializer[:]
    g.initializer.extend(keep)
    nodes = casts + list(g.node)
    del g.node[:]
    g.node.extend(nodes)
    onnx.checker.check_model(m)
    onnx.save(m, str(dst))
    return dst.stat().st_size


def load_net(ckpt: Path) -> tuple[Net, dict]:
    state = torch.load(ckpt, map_location="cpu", weights_only=True)
    net = Net(**state["config"])
    net.load_state_dict(state["model"])
    return net.float().eval(), state


def positions(n: int) -> list[tuple[str, str]]:
    """(name, fen) for the edge positions with legal moves, then ``n`` seeded ones."""
    out = [(name, fen) for name, fen in webref.EDGE_FENS if any(chess.Board(fen).legal_moves)]
    out += [(f"seeded {i}", fen) for i, (fen, _) in enumerate(webref.seeded_positions(n))]
    return [(name, fen) for name, fen in out if any(chess.Board(fen).legal_moves)]


def ort_logits(path: Path, planes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
    pol, wdl = sess.run(["policy", "wdl"], {"planes": planes})
    return pol, wdl


def legal_top(board: chess.Board, logits: np.ndarray) -> tuple[str, int, float, float]:
    """Legal arg-max (uci, index, logit) and the margin to the second-best legal logit."""
    moves, idx = encode.legal_indices(board)
    lg = logits[idx]
    order = np.argsort(-lg, kind="stable")
    best = int(order[0])
    margin = float(lg[order[0]] - lg[order[1]]) if len(order) > 1 else float("inf")
    return moves[best].uci(), int(idx[best]), float(lg[best]), margin


def compare(boards: list[chess.Board], ref: tuple[np.ndarray, np.ndarray], got: tuple[np.ndarray, np.ndarray],
            atol: float) -> dict[str, object]:
    pol_diff = float(np.abs(ref[0] - got[0]).max())
    wdl_diff = float(np.abs(ref[1] - got[1]).max())
    same, checked, near_ties, mismatches = 0, 0, 0, []
    for i, b in enumerate(boards):
        r = legal_top(b, ref[0][i])
        g = legal_top(b, got[0][i])
        if r[3] <= 2 * atol:
            near_ties += 1
            continue
        checked += 1
        if r[0] == g[0]:
            same += 1
        else:
            mismatches.append({"fen": b.fen(), "ref": r[0], "got": g[0]})
    return {
        "max_abs_diff_policy": pol_diff,
        "max_abs_diff_wdl": wdl_diff,
        "top1_checked": checked,
        "top1_same": same,
        "top1_near_ties_skipped": near_ties,
        "top1_mismatches": mismatches[:20],
        "pass": pol_diff <= atol and wdl_diff <= atol and same == checked,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", type=Path, default=Path("D:/chess-lab-data/runs/sup-v1/ckpt_080000.pt"))
    ap.add_argument("--rated-onnx", type=Path, default=None, help="default: the checkpoint's .onnx (the file the ladder rated)")
    ap.add_argument("--out", type=Path, default=hw.DATA_ROOT / "export")
    ap.add_argument("--name", default="sup-v1-final")
    ap.add_argument("--int8", action="store_true")
    ap.add_argument("--fp16", action="store_true", help="also write fp16-weight storage (compute stays fp32)")
    ap.add_argument("--n", type=int, default=256)
    ap.add_argument("--atol", type=float, default=1e-3)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()
    hw.check_data_dir(args.out)
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    net, state = load_net(args.ckpt)
    rated = args.rated_onnx or args.ckpt.with_suffix(".onnx")
    fp32 = args.out / f"{args.name}.onnx"
    export_onnx(net, fp32)
    fp32_sha = hw.sha256_file(fp32)
    rated_sha = hw.sha256_file(rated)
    int8 = args.out / f"{args.name}.int8.onnx"
    if args.int8:
        quantize_int8(fp32, int8)
    fp16 = args.out / f"{args.name}.fp16w.onnx"
    if args.fp16:
        fp16_weights(fp32, fp16)

    named = positions(args.n)
    boards = [chess.Board(fen) for _, fen in named]
    planes = encode.planes_np(np.stack([encode.compact(b) for b in boards]))
    with torch.no_grad():
        tp, tw = net(torch.from_numpy(planes))
    torch_out = (tp.numpy(), tw.numpy())

    files = {"fp32_reexport": fp32, "fp32_rated": rated}
    outs = {k: ort_logits(p, planes) for k, p in files.items()}
    parity = {k: compare(boards, torch_out, v, args.atol) for k, v in outs.items()}
    parity["reexport_vs_rated"] = compare(boards, outs["fp32_rated"], outs["fp32_reexport"], args.atol)
    def agreement(path: Path, note: str) -> dict[str, object]:
        c = compare(boards, torch_out, ort_logits(path, planes), args.atol)
        return {
            "file": path.name,
            "bytes": path.stat().st_size,
            "sha256": hw.sha256_file(path),
            "legal_top1_agreement_with_torch": c["top1_same"] / max(c["top1_checked"], 1),
            "legal_top1_same": c["top1_same"],
            "legal_top1_checked": c["top1_checked"],
            "max_abs_diff_policy": c["max_abs_diff_policy"],
            "max_abs_diff_wdl": c["max_abs_diff_wdl"],
            "note": note,
        }

    int8_report = agreement(int8, "agreement, not parity: int8 weights change the logits by design; "
                                  "not the rated file") if args.int8 else None
    fp16_report = agreement(fp16, "agreement, not parity: float16 weight storage rounds every weight; "
                                  "compute is float32; not the rated file") if args.fp16 else None

    # The browser serves the rated bytes when the re-export is identical, else the re-export.
    shipped = fp32
    ship_note = "re-export is byte-identical to the rated file" if fp32_sha == rated_sha else \
        "re-export differs in bytes from the rated file; logit parity with it is in parity.reexport_vs_rated"

    per_position = []
    rated_pol = outs["fp32_rated"][0]
    for (name, fen), b, lg in zip(named, boards, rated_pol):
        uci, idx, logit, margin = legal_top(b, lg)
        per_position.append({"name": name, "fen": fen, "top1": uci, "index": idx, "logit": round(logit, 6),
                             "margin": round(margin, 6) if np.isfinite(margin) else None})

    model = onnx.load(str(shipped))
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "encoding": webref.ENCODING,
        "inputs": {"planes": [None, encode.PLANES, 8, 8]},
        "outputs": {"policy": [None, encode.POLICY_SIZE], "wdl": [None, 3]},
        "models": [
            {"id": "fp32", "file": shipped.name, "bytes": shipped.stat().st_size, "sha256": hw.sha256_file(shipped),
             "rated": fp32_sha == rated_sha, "source_checkpoint": args.ckpt.name, "step": state["step"]},
        ],
    }
    for mid, rep in (("int8", int8_report), ("fp16w", fp16_report)):
        if rep is not None:
            manifest["models"].append({"id": mid, "file": rep["file"], "bytes": rep["bytes"], "sha256": rep["sha256"],
                                       "rated": False, "source_checkpoint": args.ckpt.name, "step": state["step"]})
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")

    receipt = {
        "schema": "chess-lab/web-parity/v1",
        "checkpoint": str(args.ckpt),
        "step": state["step"],
        "config": state["config"],
        "opset": model.opset_import[0].version,
        "rated_onnx": {"file": str(rated), "bytes": rated.stat().st_size, "sha256": rated_sha},
        "reexport": {"file": str(fp32), "bytes": fp32.stat().st_size, "sha256": fp32_sha,
                     "byte_identical_to_rated": fp32_sha == rated_sha},
        "shipped": {"file": shipped.name, "note": ship_note},
        "int8": int8_report,
        "fp16_weights": fp16_report,
        "positions": {"edge_with_legal_moves": sum(1 for n, _ in named if not n.startswith("seeded")),
                      "seeded": args.n, "seed_base": webref.POSITION_SEED_BASE, "total": len(named)},
        "tolerance": {"atol_logits": args.atol,
                      "top1_rule": "same legal arg-max wherever the reference's best two legal logits differ by more than 2 * atol"},
        "parity": parity,
        "pass": all(v["pass"] for v in parity.values()),
        "versions": {"torch": torch.__version__, "onnx": onnx.__version__, "onnxruntime": ort.__version__},
        "hardware": hw.hardware(),
        "commit": hw.git_commit(),
        "wall_s": round(time.monotonic() - t0, 1),
        "per_position": per_position,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8", newline="\n")
    summary = {k: v for k, v in receipt.items() if k not in ("per_position", "hardware")}
    print(json.dumps(summary, indent=1))
    return 0 if receipt["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
