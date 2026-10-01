"""Extract training positions from a Lichess standard rated database file.

Input: a byte prefix of a monthly ``lichess_db_standard_rated_YYYY-MM.pgn.zst``
(the Lichess database is CC0). The prefix is bounded by construction; the last
zstd frame is usually cut, so decoding stops at the first error and the last,
possibly partial, game is dropped.

Game filter (header regexes, before any move parsing):

- ``Event`` is a rated Blitz, Rapid or Classical game (no Bullet, UltraBullet or
  Correspondence, as in Maia);
- both ``WhiteElo`` and ``BlackElo`` in ``[elo_lo, elo_hi]``;
- ``Result`` decided or drawn (not ``*``); ``Termination`` is ``Normal`` or
  ``Time forfeit``.

Position filter: a position is kept unless the move played from it is an
under-promotion (no policy index) or the mover had less than ``MIN_CLOCK_S``
seconds left after the move (``%clk``; Maia drops these time-scramble moves
too). Positions without a clock comment are kept.

Output shards (``.npz``): ``x`` (N, 67) uint8 compact positions, ``y`` (N,)
uint16 policy index of the move played, ``z`` (N,) int8 game result from the
mover's side (+1, 0, -1), ``g`` (N,) uint32 game number, ``ply`` (N,) uint16.
Game ``g`` goes to the validation split when ``g % VAL_EVERY == 0``.
"""

from __future__ import annotations

import io
import json
import multiprocessing as mp
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.pgn
import numpy as np
import zstandard

from chesslab import encode, hw

MIN_CLOCK_S = 30.0
VAL_EVERY = 50
SPEEDS = ("Rated Blitz game", "Rated Rapid game", "Rated Classical game")
TERMINATIONS = ("Normal", "Time forfeit")
HDR = re.compile(r'^\[(\w+) "(.*)"\]\s*$')


@dataclass(frozen=True)
class Filter:
    elo_lo: int
    elo_hi: int

    def keep(self, h: dict[str, str]) -> bool:
        if not any(s in h.get("Event", "") for s in SPEEDS):
            return False
        if h.get("Result") not in ("1-0", "0-1", "1/2-1/2"):
            return False
        if h.get("Termination") not in TERMINATIONS:
            return False
        try:
            we, be = int(h["WhiteElo"]), int(h["BlackElo"])
        except (KeyError, ValueError):
            return False
        return self.elo_lo <= we <= self.elo_hi and self.elo_lo <= be <= self.elo_hi


def iter_games(path: Path, stats: dict[str, int]):
    """Yield (headers, raw game text) from a possibly truncated .pgn.zst."""
    dctx = zstandard.ZstdDecompressor()
    with open(path, "rb") as raw:
        reader = io.TextIOWrapper(dctx.stream_reader(raw, read_across_frames=True), encoding="utf-8", errors="replace")
        lines: list[str] = []
        headers: dict[str, str] = {}
        try:
            for line in reader:
                if line.startswith("[Event ") and lines:
                    stats["games_seen"] += 1
                    yield headers, "".join(lines)
                    lines, headers = [], {}
                m = HDR.match(line)
                if m:
                    headers[m.group(1)] = m.group(2)
                lines.append(line)
        except zstandard.ZstdError:
            stats["truncated_tail"] = 1
    # The last buffered game may be cut mid-movetext: drop it on purpose.


def encode_game(item: tuple[int, str]) -> tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    gno, text = item
    game = chess.pgn.read_game(io.StringIO(text))
    if game is None or game.errors:
        return gno, *(np.empty((0, 67), np.uint8), np.empty(0, np.uint16), np.empty(0, np.int8), np.empty(0, np.uint16)), 1
    res = {"1-0": 1, "0-1": -1}.get(game.headers.get("Result", ""), 0)
    board = game.board()
    xs, ys, zs, ps = [], [], [], []
    for node in game.mainline():
        move = node.move
        idx = encode.move_index(board, move)
        clk = node.clock()
        if idx is not None and (clk is None or clk >= MIN_CLOCK_S):
            xs.append(encode.compact(board))
            ys.append(idx)
            zs.append(res if board.turn == chess.WHITE else -res)
            ps.append(board.ply())
        board.push(move)
    if not xs:
        return gno, np.empty((0, 67), np.uint8), np.empty(0, np.uint16), np.empty(0, np.int8), np.empty(0, np.uint16), 0
    return gno, np.stack(xs), np.asarray(ys, np.uint16), np.asarray(zs, np.int8), np.asarray(ps, np.uint16), 0


def _init() -> None:
    hw.set_low_priority()


def extract(src: Path, out: Path, flt: Filter, max_games: int, workers: int, shard_positions: int = 2_000_000) -> dict:
    hw.check_data_dir(out)
    out.mkdir(parents=True, exist_ok=True)
    stats = {"games_seen": 0, "games_kept": 0, "games_parse_errors": 0, "truncated_tail": 0}
    t0 = time.monotonic()

    def kept():
        for h, text in iter_games(src, stats):
            if stats["games_kept"] >= max_games:
                return
            if flt.keep(h):
                gno = stats["games_kept"]
                stats["games_kept"] += 1
                yield gno, text

    buf: dict[str, list[np.ndarray]] = {k: [] for k in "xyzgp"}
    buffered = 0
    shards: list[dict[str, object]] = []
    positions = {"train": 0, "val": 0}

    def flush() -> None:
        nonlocal buffered
        if not buffered:
            return
        arr = {k: np.concatenate(v) for k, v in buf.items()}
        name = f"shard_{len(shards):04d}.npz"
        np.savez(out / name, x=arr["x"], y=arr["y"], z=arr["z"], g=arr["g"], ply=arr["p"])
        val = int((arr["g"] % VAL_EVERY == 0).sum())
        positions["val"] += val
        positions["train"] += len(arr["y"]) - val
        shards.append({"file": name, "positions": len(arr["y"])})
        for v in buf.values():
            v.clear()
        buffered = 0
        print(f"extract: {name}, games kept {stats['games_kept']}, seen {stats['games_seen']}, "
              f"{time.monotonic() - t0:.0f}s", file=sys.stderr, flush=True)

    with mp.get_context("spawn").Pool(workers, initializer=_init) as pool:
        for gno, x, y, z, p, err in pool.imap(encode_game, kept(), chunksize=256):
            stats["games_parse_errors"] += err
            if len(y):
                buf["x"].append(x)
                buf["y"].append(y)
                buf["z"].append(z)
                buf["g"].append(np.full(len(y), gno, np.uint32))
                buf["p"].append(p)
                buffered += len(y)
            if buffered >= shard_positions:
                flush()
    flush()
    return {
        **stats,
        "positions": positions,
        "shards": shards,
        "wall_s": round(time.monotonic() - t0, 1),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--elo-lo", type=int, default=1800)
    ap.add_argument("--elo-hi", type=int, default=2199)
    ap.add_argument("--max-games", type=int, default=1_500_000)
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--published-sha256", default="")
    ap.add_argument("--source-url", default="")
    args = ap.parse_args(argv)
    hw.set_low_priority()
    flt = Filter(args.elo_lo, args.elo_hi)
    result = extract(args.src, args.out, flt, args.max_games, args.workers)
    manifest = {
        "source_url": args.source_url,
        "source_published_sha256_full_file": args.published_sha256,
        "prefix_file": args.src.name,
        "prefix_bytes": args.src.stat().st_size,
        "prefix_sha256": hw.sha256_file(args.src),
        "license": "Lichess database exports: CC0 (database.lichess.org)",
        "filter": {
            "speeds": SPEEDS,
            "terminations": TERMINATIONS,
            "elo_both_in": [args.elo_lo, args.elo_hi],
            "min_clock_s_after_move": MIN_CLOCK_S,
            "max_games": args.max_games,
            "val_every": VAL_EVERY,
            "underpromotions": "dropped (no policy index)",
        },
        "encoding": "chesslab/encode.py (67-byte compact, 4096 from-to policy, mover-perspective result)",
        "commit": hw.git_commit(),
        "hardware": hw.hardware(),
        **result,
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: manifest[k] for k in ("games_seen", "games_kept", "positions", "wall_s")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
