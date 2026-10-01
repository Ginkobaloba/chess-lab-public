# Provenance: the run loop (jsonl records, resume by game id, spawn pool at low
# priority, one OS process per game, the process-sharing check) is adapted from
# Ginkobaloba/draughts-lab arena/ladder.py at commit
# 0a5c5a0fe6cc3443565937a738509f5de9479b19 (Paradigm-owned, MIT). Planning is
# rewritten around plain player specs instead of a weights manifest.
"""Play pairings between named ladder players and record every game.

Game ``i`` of pairing ``a~b``: ``a`` is White when ``i`` is even; the opening is
book entry ``(i // 2) % BOOK_SIZE``; the seed is ``derive_seed(run_id, pairing, i)``.

Usage:

    python -m chesslab.ladder --out D:/chess-lab-data/arena/<name> --run-id <id> \
        --player random=random --player sf-d1=sf:depth=1 ... \
        [--pairs all | --pairs a~b c~d] [--games 200] [--workers 16]

Records are appended to ``games.jsonl``; rerunning the same command resumes.
"""

from __future__ import annotations

import argparse
import itertools
import json
import multiprocessing as mp
import re
import sys
import time
from pathlib import Path

from chesslab import hw
from chesslab.game import GameTask, play
from chesslab.openings import BOOK_SIZE, load_openings
from chesslab.seeds import derive_seed

# The named rungs. TC "A" (primary): Stockfish rungs with a strength limiter
# search 100k nodes per move (about 0.1 s on one i9-13900KF thread).
RUNGS: dict[str, str] = {
    "random": "random",
    "material1": "material1",
    "sf-d1": "sf:depth=1",
    "sf-skill0": "sf:skill=0,nodes=100000",
    "sf-d3": "sf:depth=3",
    "sf-elo1320": "sf:elo=1320,nodes=100000",
    # Ladder v2 gap fillers and calibration checks (receipts/ladder-v1/NOTES.md).
    "m1r50": "mix:50:random|material1",
    "material2": "material2",
    "sf1320m1": "mix:50:material1|sf:elo=1320,nodes=100000",
    "sf-elo1500": "sf:elo=1500,nodes=100000",
    "sf-elo1700": "sf:elo=1700,nodes=100000",
    "sf-d2": "sf:depth=2",
    # TC "B": the same 1320 pin at 1M nodes per move (about 1 s), for the drift check.
    "sf-elo1320-1m": "sf:elo=1320,nodes=1000000",
}
ANCHOR = "sf-elo1320"
ANCHOR_ELO = 1320.0
TC_LABEL = {
    "A": "Stockfish 19, 1 thread, 100k nodes/move for UCI_Elo/Skill rungs; fixed depth for depth rungs",
    "B": "Stockfish 19, 1 thread, 1M nodes/move for the UCI_Elo 1320 rung",
}
_TC_B_NODES = 1_000_000


def tc_of(spec: str) -> str:
    """Return the time-control key ("A" or "B") a player spec runs at.

    Every rung defaults to time control A (TC_LABEL["A"]): non-Stockfish
    players, fixed-depth Stockfish rungs, and UCI_Elo/skill-limited rungs at
    the 100k-node budget. A rung is time control B only when its spec pins
    the node budget to the 1M-node drift-check value (see the "sf-elo1320-1m"
    entry in RUNGS above).
    """
    m = re.search(r"nodes=(\d+)", spec)
    return "B" if m and int(m.group(1)) == _TC_B_NODES else "A"


def tc_label(specs: dict[str, str], anchor: str = ANCHOR) -> str:
    """Build the "time control ..." clause of the rating label from a run's player specs.

    ``specs`` should be restricted to the players that actually appear in the
    report (e.g. the joint fit), not the full RUNGS table, so an unrelated
    rung never leaks into the label. If every player shares the anchor's time
    control, this returns the plain "A: <TC_LABEL A>" (or B) form used
    historically. If a run mixes time controls (e.g. the anchor at TC A and a
    rung at TC B, as in receipts/tcb), it names the anchor's time control and
    each non-default rung's time control explicitly instead of claiming a
    single time control for the whole run.
    """
    anchor_tc = tc_of(specs.get(anchor, RUNGS.get(anchor, "")))
    non_default = sorted(
        name for name, spec in specs.items() if name != anchor and tc_of(spec) != anchor_tc
    )
    if not non_default:
        return f"{anchor_tc}: {TC_LABEL[anchor_tc]}"
    parts = [f"{anchor_tc} (anchor {anchor}: {TC_LABEL[anchor_tc]})"]
    for name in non_default:
        tc = tc_of(specs[name])
        parts.append(f"{name} at time control {tc} ({TC_LABEL[tc]})")
    return "; ".join(parts)


def pairing_id(a: str, b: str) -> str:
    return f"{a}~{b}"


def pairing_tasks(run_id: str, a: str, a_spec: str, b: str, b_spec: str, games: int) -> list[GameTask]:
    book = load_openings()
    pid = pairing_id(a, b)
    tasks = []
    for i in range(games):
        k = (i // 2) % BOOK_SIZE
        tasks.append(
            GameTask(
                game_id=f"{pid}#{i}",
                pairing=pid,
                a=a,
                b=b,
                a_spec=a_spec,
                b_spec=b_spec,
                a_is_white=(i % 2 == 0),
                seed=derive_seed(run_id, pid, i),
                opening_index=k,
                opening=tuple(book[k]),
            )
        )
    return tasks


def read_records(path: Path) -> dict[str, dict[str, object]]:
    done: dict[str, dict[str, object]] = {}
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.endswith("\n"):  # a torn final line from a kill is ignored
                    rec = json.loads(line)
                    done[rec["game_id"]] = rec
    return done


def safe_play(task: GameTask) -> dict[str, object]:
    """``play`` that turns a crash (for example a Stockfish start-up timeout under load) into an
    error row instead of killing the whole run; errored games are not recorded and a rerun plays them."""
    try:
        return play(task).to_json()
    except Exception as exc:  # noqa: BLE001 -- any failure of one game must not end the run
        return {"error": f"{type(exc).__name__}: {exc}", "game_id": task.game_id}


def run_tasks(
    tasks: list[GameTask], out_file: Path, workers: int, progress_s: float = 60.0
) -> dict[str, dict[str, object]]:
    """Play every task not yet in ``out_file``; returns all records by game id."""
    done = read_records(out_file)
    if out_file.exists():
        text = out_file.read_bytes()
        cut = text.rfind(b"\n") + 1
        if cut != len(text):
            out_file.write_bytes(text[:cut])
    todo = [t for t in tasks if t.game_id not in done]
    if not todo:
        return done
    ctx = mp.get_context("spawn")
    t0 = last = time.monotonic()
    n = 0
    with (
        open(out_file, "a", encoding="utf-8", newline="\n") as fh,
        ctx.Pool(workers, initializer=hw.set_low_priority, maxtasksperchild=1) as pool,
    ):
        for row in pool.imap_unordered(safe_play, todo, chunksize=1):
            n += 1
            if "error" in row:
                print(f"ladder: game {row['game_id']} failed ({row['error']}); rerun to replay it",
                      file=sys.stderr, flush=True)
                continue
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            done[str(row["game_id"])] = row
            if time.monotonic() - last > progress_s:
                fh.flush()
                last = time.monotonic()
                rate = n / (last - t0)
                print(
                    f"ladder: {n}/{len(todo)} games, {rate:.2f}/s, eta {(len(todo) - n) / rate / 60:.1f} min",
                    file=sys.stderr,
                    flush=True,
                )
    return done


def check_one_process_per_game(records: list[dict[str, object]]) -> int:
    """Games that shared an OS process with another game (0 is the goal); keyed by (pid, start time)."""
    seen: set[tuple[int, float]] = set()
    shared = 0
    for r in records:
        key = (int(r["pid"]), float(r["proc_started"]))
        if key in seen:
            shared += 1
        seen.add(key)
    return shared


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--player", action="append", default=[], help="name=spec, or a RUNGS name")
    ap.add_argument("--pairs", nargs="*", default=["all"], help="'all' (round robin) or a~b entries")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--label", default="")
    args = ap.parse_args(argv)
    hw.set_low_priority()
    hw.check_data_dir(args.out)
    players: dict[str, str] = {}
    for p in args.player:
        name, _, spec = p.partition("=")
        players[name] = spec or RUNGS[name]
    if args.pairs == ["all"]:
        pairs = list(itertools.combinations(players, 2))
    else:
        pairs = [tuple(p.split("~")) for p in args.pairs]
    tasks: list[GameTask] = []
    for a, b in pairs:
        tasks += pairing_tasks(args.run_id, a, players[a], b, players[b], args.games)
    args.out.mkdir(parents=True, exist_ok=True)
    cfg_path = args.out / "ladder-config.json"
    old = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    if old and (old["run_id"] != args.run_id or old["games"] != args.games):
        raise SystemExit(f"{cfg_path} has a different run_id/games; refusing to mix")
    config = {
        "run_id": args.run_id,
        "games": args.games,
        "players": {**old.get("players", {}), **players},
        "pairs": sorted({*map(tuple, old.get("pairs", [])), *pairs}),
        "workers": args.workers,
        "label": args.label,
        "process_per_game": True,
        "seed_formula": "derive_seed(run_id, pairing_id, game_index); chesslab/seeds.py",
        "commit": hw.git_commit(),
        "hardware": hw.hardware(),
        "started": old.get("started", time.strftime("%Y-%m-%dT%H:%M:%S%z")),
    }
    print(f"ladder: {len(tasks)} games planned over {len(pairs)} pairings", file=sys.stderr)
    t0 = time.monotonic()
    records = run_tasks(tasks, args.out / "games.jsonl", args.workers)
    config["wall_s"] = round(old.get("wall_s", 0.0) + time.monotonic() - t0, 1)
    config["games_total"] = len(records)
    config["shared_process_games"] = check_one_process_per_game(list(records.values()))
    cfg_path.write_text(json.dumps(config, indent=1) + "\n", encoding="utf-8", newline="\n")
    missing = [t.game_id for t in tasks if t.game_id not in records]
    print(
        f"ladder: {len(records)} games recorded, {len(missing)} missing, "
        f"shared-process games {config['shared_process_games']}",
        file=sys.stderr,
    )
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
