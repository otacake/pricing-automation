from __future__ import annotations

"""Lexicographic no-regression guard for pricing candidates.

The only supported policy pair is objective=maximize_min_irr and
tie_break=lower_premium. load_auto_cycle_policy rejects every other pair.
There is no switch to another criterion.

Order, best first:
1. fewer hard-constraint violations (zero first)
2. higher minimum IRR among non-watch model points
3. lower total gross annual premium among non-watch model points
"""

import math
from dataclasses import dataclass
from typing import Mapping

IRR_TOLERANCE = 1e-8
PREMIUM_TOLERANCE = 1e-4


class NonFiniteMetricsError(ValueError):
    """Raised when the incumbent IRR or premium is not a finite number."""


@dataclass(frozen=True)
class LexMetrics:
    violation_count: int
    min_irr: float
    premium: float

    def as_dict(self) -> dict[str, float]:
        return {
            "violation_count": int(self.violation_count),
            "min_irr": float(self.min_irr),
            "premium": float(self.premium),
        }


def metrics_from_run_summary(summary: Mapping[str, object]) -> LexMetrics:
    summary_block = summary.get("summary")
    if not isinstance(summary_block, Mapping):
        raise ValueError("run summary is missing summary block.")
    points = summary.get("model_points")
    if not isinstance(points, list) or not points:
        raise ValueError("run summary is missing model points.")
    active = [point for point in points if isinstance(point, Mapping) and not point.get("watch")]
    if not active:
        active = [point for point in points if isinstance(point, Mapping)]
    irrs: list[float] = []
    premiums: list[float] = []
    finite = True
    for point in active:
        metrics = point.get("metrics")
        if not isinstance(metrics, Mapping):
            raise ValueError("model point is missing metrics.")
        irr = float(metrics["irr"])
        premium = float(metrics["gross_annual_premium"])
        if not math.isfinite(irr) or not math.isfinite(premium):
            finite = False
            continue
        irrs.append(irr)
        premiums.append(premium)
    if not finite:
        return LexMetrics(
            violation_count=int(summary_block["violation_count"]),
            min_irr=float("nan"),
            premium=float("nan"),
        )
    return LexMetrics(
        violation_count=int(summary_block["violation_count"]),
        min_irr=min(irrs),
        premium=sum(premiums),
    )


def _metrics_are_finite(metrics: LexMetrics) -> bool:
    return math.isfinite(metrics.min_irr) and math.isfinite(metrics.premium)


def compare_lexicographic(candidate: LexMetrics, incumbent: LexMetrics) -> int:
    """Return -1 when candidate is better, 1 when worse, 0 on a tie."""
    if candidate.violation_count != incumbent.violation_count:
        return -1 if candidate.violation_count < incumbent.violation_count else 1
    irr_delta = candidate.min_irr - incumbent.min_irr
    if irr_delta > IRR_TOLERANCE:
        return -1
    if irr_delta < -IRR_TOLERANCE:
        return 1
    premium_delta = candidate.premium - incumbent.premium
    if premium_delta < -PREMIUM_TOLERANCE:
        return -1
    if premium_delta > PREMIUM_TOLERANCE:
        return 1
    return 0


def acceptance_decision(candidate: LexMetrics, incumbent: LexMetrics) -> tuple[str, str]:
    """Return (decision, reason). decision is 'accepted' or 'rejected'.

    Non-finite candidate IRR or premium is rejected and is not an improvement.
    Non-finite incumbent metrics stop the comparison.
    """
    if not _metrics_are_finite(incumbent):
        raise NonFiniteMetricsError(
            "Incumbent IRR and premium must be finite before comparison."
        )
    if not _metrics_are_finite(candidate):
        return "rejected", "non_finite_metrics"
    comparison = compare_lexicographic(candidate, incumbent)
    if comparison < 0:
        return "accepted", "lexicographic_improvement"
    if candidate.violation_count > incumbent.violation_count:
        return "rejected", "violation_count_increased"
    if comparison > 0:
        return "rejected", "lexicographic_objective_worse"
    return "rejected", "no_improvement"
