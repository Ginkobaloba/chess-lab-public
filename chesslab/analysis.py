"""Chain checks for the engine ladder (council memo, CRUX-1 and reversal triggers).

Every function here reads recorded games only; nothing is re-played.

- ``fit``: one joint Bradley-Terry fit over all pairings (chesslab/stats.py),
  shifted so the anchor sits at ``ANCHOR_ELO``, with a stratified bootstrap CI.
- ``pair_table``: observed score (Wilson 95% CI) vs the score the joint fit
  predicts, per pairing. ``miss_pts`` is how far (in score points, 0..100) the
  prediction falls outside the observed interval; the memo's trigger is > 10.
- ``adjacent``: players sorted by fitted Elo; each adjacent pair's head-to-head
  score should lie in [0.20, 0.80] for the link to carry information.
- ``routes``: two-route agreement. For every triple (i, j, k) whose three
  pairings are all unsaturated (observed score strictly inside [0.02, 0.98]),
  the direct pairwise Elo difference i-k is compared with the two-link route
  i-j plus j-k; the residual is the cycle residual. The memo's trigger is any
  |residual| > 150 Elo.
"""

from __future__ import annotations

import itertools
import json
import math
from collections.abc import Iterable
from pathlib import Path

from chesslab.stats import EloFit, PairCounts, aggregate, elo_bootstrap, expected_score, wilson

SATURATED = 0.02


def load_games(paths: Iterable[Path]) -> list[dict[str, object]]:
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            out += [json.loads(line) for line in fh if line.endswith("\n")]
    return out


def counts(games: list[dict[str, object]]) -> list[PairCounts]:
    return aggregate((str(g["a"]), str(g["b"]), float(g["score_a"])) for g in games)


def fit(pairs: list[PairCounts], anchor: str, anchor_elo: float, resamples: int = 1000, seed: int = 0) -> EloFit:
    f = elo_bootstrap(pairs, anchor=anchor, resamples=resamples, seed=seed)
    f.elo = {k: v + anchor_elo for k, v in f.elo.items()}
    f.ci = {k: (lo + anchor_elo, hi + anchor_elo) for k, (lo, hi) in f.ci.items()}
    f.samples = f.samples + anchor_elo
    return f


def pair_elo(p: PairCounts) -> float:
    """Pairwise Elo difference a - b from the head-to-head score, with one virtual draw."""
    s = (p.wins + 0.5 * p.draws + 0.5) / (p.games + 1)
    return 400.0 * math.log10(s / (1.0 - s))


def pair_table(pairs: list[PairCounts], f: EloFit) -> list[dict[str, object]]:
    rows = []
    for p in pairs:
        lo, hi = wilson(p.wins + 0.5 * p.draws, p.games)
        pred = expected_score(f.elo[p.a], f.elo[p.b])
        miss = max(0.0, lo - pred, pred - hi) * 100.0
        rows.append(
            {
                "pair": f"{p.a}~{p.b}",
                "games": p.games,
                "w_d_l": [p.wins, p.draws, p.losses],
                "score": round(p.score, 4),
                "score_ci95": [round(lo, 4), round(hi, 4)],
                "predicted": round(pred, 4),
                "miss_pts": round(miss, 2),
                "saturated": not (SATURATED < p.score < 1 - SATURATED),
            }
        )
    return rows


def _lookup(pairs: list[PairCounts]) -> dict[tuple[str, str], PairCounts]:
    table = {}
    for p in pairs:
        table[(p.a, p.b)] = p
        table[(p.b, p.a)] = PairCounts(p.b, p.a, p.losses, p.draws, p.wins)
    return table


def adjacent(pairs: list[PairCounts], f: EloFit) -> list[dict[str, object]]:
    order = sorted(f.elo, key=f.elo.get)
    table = _lookup(pairs)
    rows = []
    for lo_p, hi_p in itertools.pairwise(order):
        p = table.get((hi_p, lo_p))
        score = None if p is None else p.score
        rows.append(
            {
                "link": f"{hi_p} over {lo_p}",
                "games": 0 if p is None else p.games,
                "score_upper": None if score is None else round(score, 4),
                "in_band_20_80": score is not None and 0.2 <= score <= 0.8,
            }
        )
    return rows


def routes(pairs: list[PairCounts]) -> list[dict[str, object]]:
    table = _lookup(pairs)
    ok = {k for k, p in table.items() if SATURATED < p.score < 1 - SATURATED}
    names = sorted({n for k in table for n in k})
    rows = []
    for i, k in itertools.combinations(names, 2):
        if (i, k) not in ok:
            continue
        direct = pair_elo(table[(i, k)])
        for j in names:
            if j in (i, k) or (i, j) not in ok or (j, k) not in ok:
                continue
            via = pair_elo(table[(i, j)]) + pair_elo(table[(j, k)])
            rows.append(
                {"from": i, "to": k, "via": j, "direct": round(direct, 1), "route": round(via, 1),
                 "residual": round(via - direct, 1)}
            )
    return rows
