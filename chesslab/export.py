"""ONNX export (and optional int8 weight quantization) of the policy + value net.

The exported graph takes ``planes`` (N, 19, 8, 8) float32 and returns
``policy`` (N, 4096) logits and ``wdl`` (N, 3) logits. The arena rates the
ONNX file through onnxruntime, so the rated artifact is the shipped artifact.
Pattern follows draughts-lab's export step (weights exported per generation
with sizes recorded); the code is new because that export targets a different
network.
"""

from __future__ import annotations

import copy
from pathlib import Path

import torch

from chesslab.encode import PLANES


def export_onnx(net: torch.nn.Module, path: Path, opset: int = 17) -> int:
    m = copy.deepcopy(net).float().eval().cpu().to(memory_format=torch.contiguous_format)
    x = torch.zeros(1, PLANES, 8, 8)
    torch.onnx.export(
        m, (x,), str(path), input_names=["planes"], output_names=["policy", "wdl"],
        dynamic_axes={"planes": {0: "n"}, "policy": {0: "n"}, "wdl": {0: "n"}}, opset_version=opset,
        dynamo=False,
    )
    return path.stat().st_size


def quantize_int8(src: Path, dst: Path) -> int:
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(str(src), str(dst), weight_type=QuantType.QInt8)
    return dst.stat().st_size
