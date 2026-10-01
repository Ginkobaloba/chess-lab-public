import chess

from chesslab import analysis
from chesslab.game import GameTask, play
from chesslab.players import make_player
from chesslab.stats import PairCounts


def test_material1_takes_free_queen():
    b = chess.Board("4k3/8/8/3q4/4P3/8/8/4K3 w - - 0 1")
    assert make_player("material1", 1).choose(b) == chess.Move.from_uci("e4d5")


def test_material2_avoids_defended_bait():
    # Pawn on d5 is defended by the queen's partner pawn on e6; material1 grabs with the queen, material2 does not.
    b = chess.Board("4k3/8/4p3/3p4/8/8/8/3QK3 w - - 0 1")
    assert make_player("material1", 1).choose(b) == chess.Move.from_uci("d1d5")
    assert make_player("material2", 1).choose(b) != chess.Move.from_uci("d1d5")


def test_mate_in_one_found():
    b = chess.Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
    for spec in ("material1", "material2"):
        assert make_player(spec, 3).choose(b) == chess.Move.from_uci("a1a8")


def test_seeded_games_repeat():
    t = GameTask("x#0", "x", "random", "material1", "random", "material1", True, 12345, 0, ("e2e4", "e7e5"))
    r1, r2 = play(t), play(t)
    assert r1.moves == r2.moves and r1.score_a == r2.score_a


def test_mix_player_is_seeded():
    b = chess.Board()
    a = [make_player("mix:50:random|material1", 7).choose(b) for _ in range(3)]
    assert len(set(a)) == 1


def test_routes_residual_zero_on_consistent_data():
    # Scores generated exactly from Elo 0 / 100 / 200: every cycle residual is small.
    # P(100 Elo) = 0.640, P(200 Elo) = 0.760.
    pairs = [PairCounts("a", "b", 640, 0, 360), PairCounts("b", "c", 640, 0, 360), PairCounts("a", "c", 760, 0, 240)]
    rows = analysis.routes(pairs)
    assert rows and all(abs(r["residual"]) < 15 for r in rows)


def test_diff_ci_no_gap_ci_contains_zero():
    # a and b have identical records against the anchor r: their fitted Elo should
    # match closely and the paired bootstrap CI on the difference should contain 0.
    pairs = [PairCounts("a", "r", 500, 0, 500), PairCounts("b", "r", 500, 0, 500)]
    f = analysis.fit(pairs, "r", 1000.0, resamples=200, seed=0)
    delta, (lo, hi) = f.diff_ci("a", "b")
    assert abs(delta) < 5
    assert lo < 0 < hi


def test_diff_ci_detects_a_real_gap():
    # a beats r at the rate a 100-Elo-stronger player would (0.640); b beats r at 0.500
    # (even with r), so a is about 100 Elo above b; the paired CI should bracket it.
    pairs = [PairCounts("a", "r", 640, 0, 360), PairCounts("b", "r", 500, 0, 500)]
    f = analysis.fit(pairs, "r", 1000.0, resamples=200, seed=0)
    delta, (lo, hi) = f.diff_ci("a", "b")
    assert 70 < delta < 130
    assert lo < 100 < hi
