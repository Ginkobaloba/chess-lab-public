"""Supervised (Maia-style) training of the policy + value net on extracted positions.

The whole training set lives on the GPU as 67-byte compact records and is
expanded to planes per batch (chesslab/model.py ``planes_torch``), so the CPU
is not in the loop. Each step samples a batch uniformly with replacement from
a seeded generator.

Loss: cross-entropy on the played move (policy) + ``value_weight`` x
cross-entropy on the game result as W/D/L from the mover's side.
Optimizer: AdamW, linear warm-up then cosine decay to 0 at ``steps``.

Checkpoints are saved at the steps in ``--ckpt-steps`` (plus step 0 and the
final step) as ``ckpt_<step>.pt`` and exported to ``ckpt_<step>.onnx``, with
validation metrics on a fixed validation subset appended to ``metrics.jsonl``.
This is what turns "rating vs training steps" into a curve.

Usage:

    python -m chesslab.train --data D:/chess-lab-data/positions/<name> --run D:/chess-lab-data/runs/<name> \
        [--steps 40000] [--batch 2048]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from chesslab import hw
from chesslab.data import VAL_EVERY
from chesslab.export import export_onnx
from chesslab.model import Net, param_count, planes_torch
from chesslab.seeds import derive_seed

DEFAULT_CKPTS = (250, 500, 1000, 2000, 4000, 8000, 16000, 24000, 32000)


def load_split(data: Path, device: torch.device, val_cap: int) -> tuple[dict, dict]:
    xs, ys, zs, vx, vy, vz = [], [], [], [], [], []
    for shard in sorted(data.glob("shard_*.npz")):
        d = np.load(shard)
        val = d["g"] % VAL_EVERY == 0
        xs.append(d["x"][~val]); ys.append(d["y"][~val]); zs.append(d["z"][~val])
        vx.append(d["x"][val]); vy.append(d["y"][val]); vz.append(d["z"][val])
    def pack(x, y, z, cap=None):
        x, y, z = np.concatenate(x), np.concatenate(y), np.concatenate(z)
        if cap is not None and len(y) > cap:
            sel = np.random.Generator(np.random.PCG64(derive_seed("val-subset"))).choice(len(y), cap, replace=False)
            sel.sort()
            x, y, z = x[sel], y[sel], z[sel]
        return {
            "x": torch.from_numpy(x).to(device),
            "y": torch.from_numpy(y.astype(np.int64)).to(device),
            "z": torch.from_numpy((1 - z.astype(np.int64))).to(device),  # +1 -> 0 (win), 0 -> 1 (draw), -1 -> 2 (loss)
        }
    return pack(xs, ys, zs), pack(vx, vy, vz, val_cap)


@torch.no_grad()
def evaluate(net: Net, val: dict, batch: int = 8192) -> dict[str, float]:
    net.eval()
    n = len(val["y"])
    top1 = pl = vl = 0.0
    for i in range(0, n, batch):
        x = planes_torch(val["x"][i : i + batch])
        with torch.autocast("cuda", dtype=torch.bfloat16):
            p, v = net(x)
        p, v = p.float(), v.float()
        y, z = val["y"][i : i + batch], val["z"][i : i + batch]
        top1 += (p.argmax(1) == y).sum().item()
        pl += F.cross_entropy(p, y, reduction="sum").item()
        vl += F.cross_entropy(v, z, reduction="sum").item()
    net.train()
    return {"val_top1": top1 / n, "val_policy_ce": pl / n, "val_value_ce": vl / n, "val_positions": n}


def lr_at(step: int, total: int, peak: float, warmup: int) -> float:
    if step < warmup:
        return peak * (step + 1) / warmup
    t = (step - warmup) / max(1, total - warmup)
    return 0.5 * peak * (1 + math.cos(math.pi * min(1.0, t)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=40_000)
    ap.add_argument("--batch", type=int, default=2048)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--wd", type=float, default=1e-4)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--value-weight", type=float, default=0.25)
    ap.add_argument("--blocks", type=int, default=8)
    ap.add_argument("--channels", type=int, default=96)
    ap.add_argument("--val-cap", type=int, default=500_000)
    ap.add_argument("--ckpt-steps", type=int, nargs="*", default=list(DEFAULT_CKPTS))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--log-every", type=int, default=200)
    args = ap.parse_args(argv)
    hw.check_data_dir(args.run)
    args.run.mkdir(parents=True, exist_ok=True)
    dev = torch.device("cuda")
    torch.manual_seed(derive_seed("init", args.seed) % (1 << 62))
    torch.backends.cudnn.benchmark = True
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    t_load = time.monotonic()
    train, val = load_split(args.data, dev, args.val_cap)
    n = len(train["y"])
    print(f"train: {n} train positions, {len(val['y'])} val positions on GPU in "
          f"{time.monotonic() - t_load:.0f}s", file=sys.stderr, flush=True)

    net = Net(args.blocks, args.channels).to(dev).to(memory_format=torch.channels_last)
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=args.wd)
    gen = torch.Generator(device=dev)
    gen.manual_seed(derive_seed("batches", args.seed) % (1 << 62))
    ckpts = sorted({0, *[s for s in args.ckpt_steps if s < args.steps], args.steps})
    config = {
        **{k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "ckpts": ckpts,
        "params": param_count(net),
        "train_positions": n,
        "commit": hw.git_commit(),
        "hardware": hw.hardware(),
        "torch": torch.__version__,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "data_manifest": json.loads((args.data / "manifest.json").read_text(encoding="utf-8")).get("prefix_sha256"),
    }
    (args.run / "train-config.json").write_text(json.dumps(config, indent=1) + "\n", encoding="utf-8", newline="\n")
    metrics = open(args.run / "metrics.jsonl", "a", encoding="utf-8", newline="\n")

    def checkpoint(step: int, wall: float) -> None:
        stem = args.run / f"ckpt_{step:06d}"
        torch.save({"step": step, "model": net.state_dict(), "config": net.config}, stem.with_suffix(".pt"))
        size = export_onnx(net, stem.with_suffix(".onnx"))
        row = {"kind": "ckpt", "step": step, "samples": step * args.batch, "wall_s": round(wall, 1),
               "onnx_bytes": size, **evaluate(net, val), "gpu": hw.gpu_snapshot()}
        metrics.write(json.dumps(row) + "\n")
        metrics.flush()
        print(f"train: ckpt {step} {row}", file=sys.stderr, flush=True)

    t0 = time.monotonic()
    net.train()
    run_loss = run_pl = 0.0
    for step in range(args.steps + 1):
        if step in ckpts:
            checkpoint(step, time.monotonic() - t0)
        if step == args.steps:
            break
        for g in opt.param_groups:
            g["lr"] = lr_at(step, args.steps, args.lr, args.warmup)
        idx = torch.randint(0, n, (args.batch,), device=dev, generator=gen)
        x = planes_torch(train["x"][idx]).contiguous(memory_format=torch.channels_last)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            p, v = net(x)
        lp = F.cross_entropy(p.float(), train["y"][idx])
        lv = F.cross_entropy(v.float(), train["z"][idx])
        loss = lp + args.value_weight * lv
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        run_loss += loss.item() if (step + 1) % args.log_every == 0 else 0.0
        if (step + 1) % args.log_every == 0:
            el = time.monotonic() - t0
            rate = (step + 1) * args.batch / el
            eta = (args.steps - step - 1) * args.batch / rate / 60
            metrics.write(json.dumps({"kind": "train", "step": step + 1, "loss": round(loss.item(), 4),
                                      "policy_ce": round(lp.item(), 4), "lr": opt.param_groups[0]["lr"],
                                      "samples_per_s": round(rate)}) + "\n")
            print(f"train: step {step + 1}/{args.steps} loss {loss.item():.4f} pol {lp.item():.4f} "
                  f"{rate:.0f} pos/s eta {eta:.1f} min", file=sys.stderr, flush=True)
    config["wall_s"] = round(time.monotonic() - t0, 1)
    config["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (args.run / "train-config.json").write_text(json.dumps(config, indent=1) + "\n", encoding="utf-8", newline="\n")
    metrics.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
