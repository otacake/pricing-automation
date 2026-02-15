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


def test_quality_gate_fails_with_strict_explainability_when_compare_integrity_missing() -> None:
    spec = {"trace_map": [{"claim_id": "a", "source_path": "$.summary.min_irr"}]}
    metrics = {"total_shape_count": 10, "editable_shape_count": 10}
    explain = {
        "causal_chain_coverage": 1.0,
        "checks": {
            "procon_cardinality_ok": True,
            "bridge_and_sensitivity_present": True,
        },
    }
    compare = {"integrity": {"independent_optimization": False}}
    result = evaluate_quality_gate(
        spec=spec,
        render_metrics=metrics,
        runtime_seconds=10.0,
        explainability_report=explain,
        decision_compare=compare,
        strict_explainability=True,
        decision_compare_enabled=True,
    )
    assert result.passed is False
    assert result.checks["dual_alternative_integrity"] is False


def test_quality_gate_fails_with_strict_explainability_when_main_narrative_missing() -> None:
    spec = {
        "trace_map": [{"claim_id": "a", "source_path": "$.summary.min_irr"}],
        "main_slide_checks": {
            "coverage": 0.5,
            "density_ok": False,
            "main_compare_present": False,
            "decision_style_ok": False,
        },
    }
    metrics = {"total_shape_count": 10, "editable_shape_count": 10}
    explain = {
        "causal_chain_coverage": 1.0,
        "checks": {
            "procon_cardinality_ok": True,
            "bridge_and_sensitivity_present": True,
        },
    }
    compare = {"integrity": {"independent_optimization": True}}
    result = evaluate_quality_gate(
        spec=spec,
        render_metrics=metrics,
        runtime_seconds=10.0,
        explainability_report=explain,
        decision_compare=compare,
        strict_explainability=True,
        decision_compare_enabled=True,
    )
    assert result.passed is False
    assert result.checks["main_narrative_coverage"] is False
    assert result.checks["main_narrative_density_ok"] is False
    assert result.checks["main_compare_present"] is False
    assert result.checks["decision_style_ok"] is False
