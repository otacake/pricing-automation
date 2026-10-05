from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.acceptance import LexMetrics, acceptance_decision, metrics_from_run_summary


def _metrics(violations: int, min_irr: float, premium: float) -> LexMetrics:
    return LexMetrics(violation_count=violations, min_irr=min_irr, premium=premium)


def test_fewer_violations_win_even_with_lower_irr() -> None:
    decision, reason = acceptance_decision(
        _metrics(0, 0.01, 100.0),
        _metrics(2, 0.05, 90.0),
    )
    assert decision == "accepted"
    assert reason == "lexicographic_improvement"


def test_more_violations_are_rejected() -> None:
    decision, reason = acceptance_decision(
        _metrics(3, 0.20, 10.0),
        _metrics(1, 0.01, 500.0),
    )
    assert decision == "rejected"
    assert reason == "violation_count_increased"


def test_higher_min_irr_wins_when_violations_match() -> None:
    decision, reason = acceptance_decision(
        _metrics(0, 0.04, 200.0),
        _metrics(0, 0.03, 100.0),
    )
    assert decision == "accepted"
    assert reason == "lexicographic_improvement"


def test_lower_min_irr_is_rejected_when_violations_match() -> None:
    decision, reason = acceptance_decision(
        _metrics(0, 0.02, 50.0),
        _metrics(0, 0.03, 80.0),
    )
    assert decision == "rejected"
    assert reason == "lexicographic_objective_worse"


def test_lower_premium_breaks_irr_ties() -> None:
    decision, reason = acceptance_decision(
        _metrics(0, 0.03, 90.0),
        _metrics(0, 0.03, 100.0),
    )
    assert decision == "accepted"
    assert reason == "lexicographic_improvement"


def test_equal_metrics_are_not_an_improvement() -> None:
    decision, reason = acceptance_decision(
        _metrics(1, 0.03, 100.0),
        _metrics(1, 0.03, 100.0),
    )
    assert decision == "rejected"
    assert reason == "no_improvement"


def test_watch_points_are_excluded_from_min_irr_and_premium() -> None:
    summary = {
        "summary": {"violation_count": 0},
        "model_points": [
            {
                "watch": False,
                "metrics": {"irr": 0.04, "gross_annual_premium": 1000.0},
            },
            {
                "watch": True,
                "metrics": {"irr": -0.5, "gross_annual_premium": 99999.0},
            },
        ],
    }
    metrics = metrics_from_run_summary(summary)
    assert metrics.violation_count == 0
    assert metrics.min_irr == 0.04
    assert metrics.premium == 1000.0
