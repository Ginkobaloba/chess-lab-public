"""Rate every exported checkpoint of a training run on the engine ladder.

Each checkpoint ``ckpt_<step>.onnx`` plays ``--games`` games against each rung
in ``--rungs`` (TC A specs from chesslab/ladder.py), recorded in
``<arena>/games.jsonl`` with the same seeding, opening and one-process-per-game
rules as the ladder. Then one joint Bradley-Terry fit covers the ladder
round-robin games (``--ladder``) plus every checkpoint game, anchored at
sf-elo1320 = 1320, and the curve (step -> Elo, 95% CI) is written to
``receipts/<name>/``.

Usage:

    python scripts/rate_checkpoints.py --run D:/chess-lab-data/runs/<run> --arena D:/chess-lab-data/arena/<name> \
        --ladder D:/chess-lab-data/arena/ladder-v1 --name <receipt name> [--games 100] [--steps 0 1000 ...]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chesslab import analysis, hw  # noqa: E402
from chesslab.ladder import ANCHOR, ANCHOR_ELO, RUNGS, TC_LABEL, check_one_process_per_game, pairing_tasks, run_tasks  # noqa: E402

LABEL = ("engine-ladder Elo (Stockfish 19 UCI_Elo 1320-anchored, time control A: {tc}), 95% CI. "
         "Not a human rating. Values below 1320 are extrapolated through the ladder chain.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--arena", type=Path, required=True)
    ap.add_argument("--ladder", type=Path, action="append", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--rungs", nargs="*", default=["random", "material1", "sf-d1", "sf-skill0", "sf-d3", "sf-elo1320"])
    ap.add_argument("--steps", type=int, nargs="*", default=None, help="only these checkpoint steps")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--fit-only", action="store_true")
    ap.add_argument("--adaptive", type=int, default=0, help="stage-2 games per pairing vs the nearest rungs (0: off)")
    ap.add_argument("--near", type=int, default=3, help="stage-2 rungs per checkpoint")
    args = ap.parse_args()
    hw.set_low_priority()
    hw.check_data_dir(args.arena)
    args.arena.mkdir(parents=True, exist_ok=True)
    ckpts = sorted(p for p in args.run.glob("ckpt_*.onnx") if p.stem.split("_")[1].isdigit())
    if args.steps is not None:
        ckpts = [c for c in ckpts if int(c.stem.split("_")[1]) in args.steps]
    run_id = f"rate:{args.run.name}"
    tasks = []
    for c in ckpts:
        name = f"net@{int(c.stem.split('_')[1])}"
        for r in args.rungs:
            tasks += pairing_tasks(run_id, name, f"net:{c.resolve()}", r, RUNGS[r], args.games)
    t0 = time.monotonic()
    games_ladder = analysis.load_games([d / "games.jsonl" for d in args.ladder])
    keep_rungs = set(args.rungs)
    games_ladder = [g for g in games_ladder if g["a"] in keep_rungs and g["b"] in keep_rungs]
    if not args.fit_only:
        print(f"rate: stage 1, {len(tasks)} games planned for {len(ckpts)} checkpoints", file=sys.stderr, flush=True)
        run_tasks(tasks, args.arena / "games.jsonl", args.workers)
        if args.adaptive:
            # Stage 2: top up to --adaptive games against the rungs nearest each checkpoint's stage-1 fit
            # (the --near closest rungs by fitted Elo), where a game carries the most information.
            g1 = analysis.load_games([args.arena / "games.jsonl"])
            f1 = analysis.fit(analysis.counts(games_ladder + g1), ANCHOR, ANCHOR_ELO, resamples=50)
            tasks2 = []
            for c in ckpts:
                name = f"net@{int(c.stem.split('_')[1])}"
                near = sorted(args.rungs, key=lambda r: abs(f1.elo[r] - f1.elo[name]))[: args.near]
                for r in near:
                    tasks2 += pairing_tasks(run_id, name, f"net:{c.resolve()}", r, RUNGS[r], args.adaptive)
            print(f"rate: stage 2, {len(tasks2)} games (incl. already played) near each checkpoint",
                  file=sys.stderr, flush=True)
            run_tasks(tasks2, args.arena / "games.jsonl", args.workers)
    wall = time.monotonic() - t0
    games_ckpt = analysis.load_games([args.arena / "games.jsonl"])
    # Only the selected rungs and checkpoints enter the fit (a no-op for a full run; used for
    # sensitivity fits such as "only the Stockfish rungs at or above the pin").
    names = {f"net@{int(c.stem.split('_')[1])}" for c in ckpts}
    games_ckpt = [g for g in games_ckpt if g["b"] in keep_rungs and g["a"] in names]
    pairs = analysis.counts(games_ladder + games_ckpt)
    f = analysis.fit(pairs, ANCHOR, ANCHOR_ELO)
    table = analysis.pair_table(pairs, f)
    metrics = {}
    for line in open(args.run / "metrics.jsonl", encoding="utf-8"):
        row = json.loads(line)
        if row.get("kind") == "ckpt":
            metrics[row["step"]] = row
    curve = []
    for n in sorted((n for n in f.elo if n.startswith("net@")), key=lambda n: int(n[4:])):
        step = int(n[4:])
        m = metrics.get(step, {})
        curve.append({
            "step": step, "samples": m.get("samples"), "elo": round(f.elo[n], 1),
            "ci95": [round(x, 1) for x in f.ci[n]], "extrapolated_below_1320": f.elo[n] < ANCHOR_ELO,
            "val_top1": m.get("val_top1"), "onnx_bytes": m.get("onnx_bytes"),
            "games": sum(p.games for p in pairs if n in (p.a, p.b)),
        })
    out = hw.REPO_ROOT / "receipts" / args.name
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.arena / "games.jsonl", out / "games.jsonl")
    for fn in ("train-config.json", "metrics.jsonl"):
        shutil.copyfile(args.run / fn, out / fn)
    result = {
        "label": LABEL.format(tc=TC_LABEL["A"]),
        "net_player": "ONNX checkpoint via onnxruntime CPU, arg-max of the legal-move policy (1 node, no search)",
        "anchor": ANCHOR, "anchor_elo": ANCHOR_ELO,
        "ladder_sources": [str(d) for d in args.ladder],
        "stage1_games_per_checkpoint_per_rung": args.games, "rungs": args.rungs,
        "stage2_games_per_pairing": args.adaptive, "stage2_nearest_rungs": args.near,
        "rating_wall_s_this_invocation": round(wall, 1),
        "commit": hw.git_commit(), "hardware": hw.hardware(),
        "shared_process_games": check_one_process_per_game(games_ckpt),
        "curve": curve,
        "rungs_fit": {n: {"elo": round(f.elo[n], 1), "ci95": [round(x, 1) for x in f.ci[n]]}
                      for n in sorted(f.elo, key=f.elo.get) if not n.startswith("net@")},
        "pairs": table,
    }
    (out / "curve.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    lines = [f"# Checkpoint ratings: {args.name}", "", f"Label: {result['label']}", "",
             f"Player: {result['net_player']}. Generated by `scripts/rate_checkpoints.py`; games in `games.jsonl`, "
             "ladder games from the ladder receipt; training facts in `train-config.json` and `metrics.jsonl`.", "",
             "| step | samples | Elo | 95% CI | val top-1 move match | games | note |", "|---|---|---|---|---|---|---|"]
    for c in curve:
        top1 = "" if c["val_top1"] is None else f"{c['val_top1']:.3f}"
        note = "extrapolated below 1320" if c["extrapolated_below_1320"] else ""
        lines.append(f"| {c['step']} | {c['samples']} | {c['elo']:.0f} | {c['ci95'][0]:.0f} to {c['ci95'][1]:.0f} | "
                     f"{top1} | {c['games']} | {note} |")
    lines += ["", "Rungs in the same fit:", ""]
    lines += [f"- {n}: {r['elo']:.0f} ({r['ci95'][0]:.0f} to {r['ci95'][1]:.0f})" for n, r in result["rungs_fit"].items()]
    lines.append("")
    (out / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = [max(c["step"], 1) for c in curve]
        ys = [c["elo"] for c in curve]
        lo = [c["elo"] - c["ci95"][0] for c in curve]
        hi = [c["ci95"][1] - c["elo"] for c in curve]
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.errorbar(xs, ys, yerr=[lo, hi], fmt="o-", capsize=3)
        ax.axhline(ANCHOR_ELO, ls="--", lw=1, color="gray")
        ax.axhspan(min(ys + [ANCHOR_ELO]) - 400, ANCHOR_ELO, color="gray", alpha=0.08)
        ax.set_xscale("log")
        ax.set_xlabel("training step (step 0 plotted at 1)")
        ax.set_ylabel("engine-ladder Elo (SF 1320-anchored)")
        ax.set_title("Rating vs training steps (shaded: extrapolated below 1320; not a human rating)", fontsize=9)
        fig.tight_layout()
        fig.savefig(out / "curve.png", dpi=110)
    except Exception as exc:  # the plot is a convenience; the receipt is curve.json
        print(f"rate: plot skipped: {exc}", file=sys.stderr)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
