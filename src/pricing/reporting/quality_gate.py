from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    numeric_trace_coverage: float
    editable_shape_ratio: float
    runtime_seconds: float
    thresholds: dict[str, float]
    checks: dict[str, bool]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "numeric_trace_coverage": self.numeric_trace_coverage,
            "editable_shape_ratio": self.editable_shape_ratio,
            "runtime_seconds": self.runtime_seconds,
            "thresholds": self.thresholds,
            "checks": self.checks,
            "details": self.details,
        }


def _safe_float(value: object, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evaluate_quality_gate(
    *,
    spec: Mapping[str, Any],
    render_metrics: Mapping[str, Any],
    runtime_seconds: float,
    min_numeric_trace_coverage: float = 1.0,
    min_editable_shape_ratio: float = 0.80,
    max_runtime_seconds: float = 180.0,
) -> QualityGateResult:
    trace_rows = spec.get("trace_map", [])
    trace_items = trace_rows if isinstance(trace_rows, list) else []
    traced = 0
    for row in trace_items:
        if isinstance(row, Mapping) and isinstance(row.get("source_path"), str) and row["source_path"].strip():
            traced += 1
    trace_coverage = 0.0 if not trace_items else (traced / len(trace_items))

    total_shapes = int(_safe_float(render_metrics.get("total_shape_count"), default=0.0))
    editable_shapes = int(_safe_float(render_metrics.get("editable_shape_count"), default=0.0))
    editable_ratio = 0.0 if total_shapes <= 0 else (editable_shapes / total_shapes)

    checks = {
        "traceability": trace_coverage >= min_numeric_trace_coverage,
        "editability": editable_ratio >= min_editable_shape_ratio,
        "runtime": runtime_seconds <= max_runtime_seconds,
    }
    thresholds = {
        "min_numeric_trace_coverage": min_numeric_trace_coverage,
        "min_editable_shape_ratio": min_editable_shape_ratio,
        "max_runtime_seconds": max_runtime_seconds,
    }
    details = {
        "trace_item_count": len(trace_items),
        "traced_item_count": traced,
        "total_shape_count": total_shapes,
        "editable_shape_count": editable_shapes,
    }
    return QualityGateResult(
        passed=all(checks.values()),
        numeric_trace_coverage=trace_coverage,
        editable_shape_ratio=editable_ratio,
        runtime_seconds=runtime_seconds,
        thresholds=thresholds,
        checks=checks,
        details=details,
    )
