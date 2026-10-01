"""Policy + value residual network, sized for browser inference.

Shape (default 8 blocks x 96 filters, about 1.5M parameters, about 6.0 MB as
fp32 ONNX, about 1.5 MB after int8 weight quantization):

- stem: 3x3 conv 19 -> C, BN, ReLU;
- trunk: ``blocks`` residual blocks (3x3 conv, BN, ReLU, 3x3 conv, BN, skip, ReLU);
- policy head: 3x3 conv C -> C, BN, ReLU, 1x1 conv C -> 64. Channel ``t`` at
  square ``f`` is the logit of the move ``f -> t``, so the 4096 logits are
  ``from * 64 + to`` (chesslab/encode.py), with no dense layer;
- value head (WDL, from the mover's side): 1x1 conv C -> 8, BN, ReLU, dense
  512 -> 128, ReLU, dense 128 -> 3. It is trained jointly at a low weight so a
  later search or RL phase can use it; the ladder player ignores it.

``planes_torch`` expands 67-byte compact records to input planes on the GPU and
must match ``encode.planes_np`` exactly (tests/test_encode.py).
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn

from chesslab.encode import PLANES


class Block(nn.Module):
    def __init__(self, c: int) -> None:
        super().__init__()
        self.c1 = nn.Conv2d(c, c, 3, padding=1, bias=False)
        self.b1 = nn.BatchNorm2d(c)
        self.c2 = nn.Conv2d(c, c, 3, padding=1, bias=False)
        self.b2 = nn.BatchNorm2d(c)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = F.relu(self.b1(self.c1(x)))
        y = self.b2(self.c2(y))
        return F.relu(x + y)


class Net(nn.Module):
    def __init__(self, blocks: int = 8, channels: int = 96) -> None:
        super().__init__()
        self.config = {"blocks": blocks, "channels": channels}
        self.stem = nn.Sequential(nn.Conv2d(PLANES, channels, 3, padding=1, bias=False), nn.BatchNorm2d(channels), nn.ReLU())
        self.trunk = nn.Sequential(*[Block(channels) for _ in range(blocks)])
        self.pol = nn.Sequential(
            nn.Conv2d(channels, channels, 3, padding=1, bias=False), nn.BatchNorm2d(channels), nn.ReLU(),
            nn.Conv2d(channels, 64, 1),
        )
        self.val_conv = nn.Sequential(nn.Conv2d(channels, 8, 1, bias=False), nn.BatchNorm2d(8), nn.ReLU())
        self.val_fc = nn.Sequential(nn.Linear(512, 128), nn.ReLU(), nn.Linear(128, 3))

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.trunk(self.stem(x))
        p = self.pol(h)  # (N, to=64, 8, 8 = from)
        policy = p.flatten(2).transpose(1, 2).flatten(1)  # (N, from*64 + to)
        wdl = self.val_fc(self.val_conv(h).flatten(1))
        return policy, wdl


def planes_torch(rec: torch.Tensor) -> torch.Tensor:
    """(N, 67) uint8 on any device to (N, 19, 8, 8) float32 planes."""
    n = rec.shape[0]
    rec = rec.long()
    sq = rec[:, :64]
    pieces = F.one_hot(sq, 13)[:, :, 1:].transpose(1, 2).float()  # (N, 12, 64)
    flags = rec[:, 64]
    castle = torch.stack([((flags >> b) & 1) for b in range(4)], 1).float()[:, :, None].expand(n, 4, 64)
    ep = rec[:, 65]
    ep_plane = torch.zeros(n, 64, device=rec.device)
    has = ep > 0
    ep_plane[has, 40 + ep[has] - 1] = 1.0
    clock = (rec[:, 66].float() / 100.0)[:, None].expand(n, 64)
    ones = torch.ones(n, 64, device=rec.device)
    x = torch.cat([pieces, castle, ep_plane[:, None], clock[:, None], ones[:, None]], 1)
    return x.view(n, PLANES, 8, 8)


def param_count(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())
