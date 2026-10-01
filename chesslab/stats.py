# Provenance: copied verbatim from Ginkobaloba/draughts-lab arena/stats.py at commit 0a5c5a0fe6cc3443565937a738509f5de9479b19
# (Paradigm-owned, MIT). Changes from the original: none.
"""Statistics for arena receipts (docs/RECEIPTS.md, "Statistics").

- Wilson score intervals (Wilson 1927) for a win rate and for a score, where a
  draw counts as half a success.
- Bradley-Terry ratings by maximum likelihood on the Elo scale
  (P(i beats j) = 1 / (1 + 10^((R_j - R_i) / 400))), draws as half a win and
  half a loss, with one anchor fixed at 0.
- A weak prior: every pair of players that met gets one virtual draw (the
  BayesElo convention). Without it a player that wins every game against every
  opponent it met has no finite maximum-likelihood rating, which is certain to
  happen in some bootstrap resamples (for example a late generation against
  ``random``). With 400 real games per pairing its effect is small, and
  ``tests/test_stats.py`` measures it.
- Percentile bootstrap over games, stratified by pairing: each resample draws
  every pairing's games with replacement (a multinomial over its win, draw and
  loss counts with the same number of games) and refits.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

Z95 = 1.959963984540054
ELO_PER_NAT = 400.0 / math.log(10.0)


def wilson(successes: float, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for ``successes`` out of ``n``; (0, 1) when n == 0."""
    if n <= 0:
        return 0.0, 1.0
    if successes < 0 or successes > n:
        raise ValueError(f"successes {successes} outside [0, {n}]")
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z / denom * math.sqrt(p * (1.0 - p) / n + z2 / (4 * n * n))
    return max(0.0, center - half), min(1.0, center + half)


@dataclass(frozen=True)
class PairCounts:
    """Games between players ``a`` and ``b`` from ``a``'s side."""

    a: str
    b: str
    wins: int
    draws: int
    losses: int

    @property
    def games(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def score(self) -> float:
        return (self.wins + 0.5 * self.draws) / self.games if self.games else float("nan")


def aggregate(records: Iterable[tuple[str, str, float]]) -> list[PairCounts]:
    """(a, b, score_a) game records to per-pairing counts (order of first appearance)."""
    table: dict[tuple[str, str], list[int]] = {}
    for a, b, s in records:
        key = (a, b)
        row = table.setdefault(key, [0, 0, 0])
        if s == 1.0:
            row[0] += 1
        elif s == 0.5:
            row[1] += 1
        elif s == 0.0:
            row[2] += 1
        else:
            raise ValueError(f"score must be 0, 0.5 or 1, got {s}")
    return [PairCounts(a, b, *row) for (a, b), row in table.items()]


def _index(pairs: Sequence[PairCounts], anchor: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for p in pairs:
        for n in (p.a, p.b):
            if n not in seen:
                seen.add(n)
                names.append(n)
    if anchor not in seen:
        raise ValueError(f"anchor {anchor!r} played no games")
    # Connectivity: every player must be linked to the anchor through games.
    adj: dict[str, set[str]] = {n: set() for n in names}
    for p in pairs:
        adj[p.a].add(p.b)
        adj[p.b].add(p.a)
    stack, reach = [anchor], {anchor}
    while stack:
        for m in adj[stack.pop()]:
            if m not in reach:
                reach.add(m)
                stack.append(m)
    if reach != seen:
        raise ValueError(f"players not connected to {anchor!r}: {sorted(seen - reach)}")
    return names


def fit_bt(
    ia: np.ndarray,
    ib: np.ndarray,
    score_a: np.ndarray,
    games: np.ndarray,
    n_players: int,
    anchor: int,
    prior_draws: float = 1.0,
    tol: float = 1e-10,
    max_iter: int = 200,
) -> np.ndarray:
    """Newton's method on the Bradley-Terry log-likelihood; ratings in natural units.

    Args:
        ia, ib: player indices per pairing.
        score_a: points scored by ``ia`` per pairing (wins + draws / 2).
        games: games per pairing.
        prior_draws: virtual draws added to each pairing (0 disables the prior).
    """
    s = score_a + 0.5 * prior_draws
    n = games + prior_draws
    free = np.array([i for i in range(n_players) if i != anchor])
    r = np.zeros(n_players)
    for _ in range(max_iter):
        p = 1.0 / (1.0 + np.exp(r[ib] - r[ia]))
        resid = s - n * p
        grad = np.zeros(n_players)
        np.add.at(grad, ia, resid)
        np.add.at(grad, ib, -resid)
        w = n * p * (1.0 - p)
        hess = np.zeros((n_players, n_players))
        np.add.at(hess, (ia, ia), -w)
        np.add.at(hess, (ib, ib), -w)
        np.add.at(hess, (ia, ib), w)
        np.add.at(hess, (ib, ia), w)
        step = np.linalg.solve(hess[np.ix_(free, free)], -grad[free])
        # The log-likelihood is concave; cap the step to keep early iterations stable.
        big = np.abs(step).max()
        if big > 2.0:
            step *= 2.0 / big
        r[free] += step
        if big < tol:
            break
    else:
        raise RuntimeError("Bradley-Terry fit did not converge")
    return r


@dataclass
class EloFit:
    players: list[str]
    elo: dict[str, float]
    ci: dict[str, tuple[float, float]]
    samples: np.ndarray  # (resamples, players) Elo, for derived intervals
    anchor: str
    prior_draws: float
    resamples: int
    seed: int

    def diff_ci(self, a: str, b: str, level: float = 0.95) -> tuple[float, tuple[float, float]]:
        """Point estimate and percentile interval of Elo(a) - Elo(b)."""
        ia, ib = self.players.index(a), self.players.index(b)
        d = self.samples[:, ia] - self.samples[:, ib]
        lo, hi = np.quantile(d, [(1 - level) / 2, 1 - (1 - level) / 2])
        return self.elo[a] - self.elo[b], (float(lo), float(hi))


def elo_bootstrap(
    pairs: Sequence[PairCounts],
    anchor: str = "random",
    resamples: int = 1000,
    seed: int = 0,
    prior_draws: float = 1.0,
    level: float = 0.95,
) -> EloFit:
    """Bradley-Terry Elo with a stratified percentile bootstrap (see module docstring)."""
    names = _index(pairs, anchor)
    pos = {n: i for i, n in enumerate(names)}
    ia = np.array([pos[p.a] for p in pairs])
    ib = np.array([pos[p.b] for p in pairs])
    counts = np.array([[p.wins, p.draws, p.losses] for p in pairs], dtype=np.int64)
    games = counts.sum(axis=1).astype(np.float64)
    a_idx = pos[anchor]

    def fit(c: np.ndarray) -> np.ndarray:
        score = c[:, 0] + 0.5 * c[:, 1]
        return fit_bt(ia, ib, score.astype(np.float64), games, len(names), a_idx, prior_draws) * ELO_PER_NAT

    point = fit(counts)
    rng = np.random.Generator(np.random.PCG64(seed))
    probs = counts / games[:, None]
    n_games = counts.sum(axis=1)
    samples = np.empty((resamples, len(names)))
    for k in range(resamples):
        samples[k] = fit(rng.multinomial(n_games, probs))
    lo, hi = np.quantile(samples, [(1 - level) / 2, 1 - (1 - level) / 2], axis=0)
    return EloFit(
        players=names,
        elo={n: float(point[i]) for i, n in enumerate(names)},
        ci={n: (float(lo[i]), float(hi[i])) for i, n in enumerate(names)},
        samples=samples,
        anchor=anchor,
        prior_draws=prior_draws,
        resamples=resamples,
        seed=seed,
    )


def expected_score(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))
