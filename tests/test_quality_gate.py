from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.reporting.quality_gate import evaluate_quality_gate


def test_quality_gate_passes_with_sufficient_metrics() -> None:
    spec = {
        "trace_map": [
            {"claim_id": "a", "source_path": "$.summary.min_irr"},
            {"claim_id": "b", "source_path": "$.summary.min_nbv"},
        ]
    }
    metrics = {"total_shape_count": 10, "editable_shape_count": 9}
    result = evaluate_quality_gate(spec=spec, render_metrics=metrics, runtime_seconds=120.0)
    assert result.passed is True
    assert result.numeric_trace_coverage == 1.0
    assert result.editable_shape_ratio == 0.9


def test_quality_gate_fails_when_traceability_is_missing() -> None:
    spec = {"trace_map": [{"claim_id": "a", "source_path": ""}]}
    metrics = {"total_shape_count": 10, "editable_shape_count": 9}
    result = evaluate_quality_gate(spec=spec, render_metrics=metrics, runtime_seconds=120.0)
    assert result.passed is False
    assert result.checks["traceability"] is False
