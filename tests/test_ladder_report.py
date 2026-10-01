"""Tests for the ladder-report time-control label (chesslab.ladder.tc_label /
tc_of, used by scripts/ladder_report.py).

Background: the label used to hardcode "time control A" regardless of which
arena was reported, because the anchor (sf-elo1320) is defined at TC A in
every run, including tcb (receipts/tcb/NOTES.md). tc_label fixes this by
reading the actual player specs and naming the anchor's time control plus any
non-default rung explicitly.
"""

import json
import sys
from pathlib import Path

from chesslab.ladder import ANCHOR, RUNGS, TC_LABEL, tc_label, tc_of
from scripts import ladder_report

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_tc_of_reads_the_node_budget():
    assert tc_of(RUNGS["sf-elo1320"]) == "A"
    assert tc_of(RUNGS["sf-d1"]) == "A"
    assert tc_of(RUNGS["random"]) == "A"
    assert tc_of(RUNGS["sf-elo1320-1m"]) == "B"


def test_tc_of_does_not_false_positive_on_a_longer_node_count():
    assert tc_of("sf:elo=1320,nodes=10000000") == "A"


def test_tc_label_pure_a_matches_the_historical_wording():
    # A run with only TC-A rungs (e.g. ladder-v2, int8-v1, sup-v1-ratings) keeps
    # exactly the wording those committed receipts already show.
    specs = {n: RUNGS[n] for n in ("sf-elo1320", "sf-d1", "sf-elo1500")}
    assert tc_label(specs, ANCHOR) == f"A: {TC_LABEL['A']}"


def test_tc_label_mixed_names_anchor_and_each_non_default_rung():
    # A run like tcb: the anchor at TC A plus one rung at TC B.
    specs = {n: RUNGS[n] for n in ("sf-elo1320", "sf-elo1320-1m", "sf-d1")}
    label = tc_label(specs, ANCHOR)
    assert label.startswith(f"A (anchor sf-elo1320: {TC_LABEL['A']})")
    assert f"sf-elo1320-1m at time control B ({TC_LABEL['B']})" in label
    # sf-d1 shares the anchor's time control, so it is not called out by name.
    assert "sf-d1 at time control" not in label


def _run_report(arena: Path, out: Path, monkeypatch, resamples: int = 20) -> dict:
    argv = [
        "ladder_report.py",
        "--name", "test-scratch",
        "--arena", str(arena),
        "--out", str(out),
        "--resamples", str(resamples),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert ladder_report.main() == 0
    return json.loads((out / "fit.json").read_text(encoding="utf-8"))


def test_ladder_report_pure_tc_a_arena_label(tmp_path, monkeypatch):
    fit = _run_report(REPO_ROOT / "receipts" / "ladder-v2", tmp_path / "out", monkeypatch)
    assert fit["label"] == ladder_report.LABEL.format(tc=f"A: {TC_LABEL['A']}")
    assert "time control B" not in fit["label"]


def test_ladder_report_mixed_tc_arena_tcb_label(tmp_path, monkeypatch):
    fit = _run_report(REPO_ROOT / "receipts" / "tcb", tmp_path / "out", monkeypatch)
    assert "time control A (anchor sf-elo1320:" in fit["label"]
    assert "sf-elo1320-1m at time control B (" in fit["label"]

    # Only the label (and the resample-count-dependent numbers) differ from the
    # committed receipt; the game set and anchor are unchanged.
    committed = json.loads((REPO_ROOT / "receipts" / "tcb" / "fit.json").read_text(encoding="utf-8"))
    assert fit["anchor"] == committed["anchor"]
    assert fit["games"] == committed["games"]
    assert set(fit["ratings"]) == set(committed["ratings"])
