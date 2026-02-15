from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    numeric_trace_coverage: float
    editable_shape_ratio: float
    runtime_seconds: float
    causal_chain_coverage: float
    procon_cardinality_ok: bool
    dual_alternative_integrity: bool
    bridge_and_sensitivity_present: bool
    main_compare_present: bool
    main_narrative_coverage: float
    main_narrative_density_ok: bool
    decision_style_ok: bool
    thresholds: dict[str, float]
    checks: dict[str, bool]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "numeric_trace_coverage": self.numeric_trace_coverage,
            "editable_shape_ratio": self.editable_shape_ratio,
            "runtime_seconds": self.runtime_seconds,
            "causal_chain_coverage": self.causal_chain_coverage,
            "procon_cardinality_ok": self.procon_cardinality_ok,
            "dual_alternative_integrity": self.dual_alternative_integrity,
            "bridge_and_sensitivity_present": self.bridge_and_sensitivity_present,
            "main_compare_present": self.main_compare_present,
            "main_narrative_coverage": self.main_narrative_coverage,
            "main_narrative_density_ok": self.main_narrative_density_ok,
            "decision_style_ok": self.decision_style_ok,
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
    explainability_report: Mapping[str, Any] | None = None,
    decision_compare: Mapping[str, Any] | None = None,
    strict_explainability: bool = False,
    decision_compare_enabled: bool = False,
    min_numeric_trace_coverage: float = 1.0,
    min_editable_shape_ratio: float = 0.80,
    max_runtime_seconds: float = 180.0,
    min_causal_chain_coverage: float = 1.0,
    min_main_narrative_coverage: float = 1.0,
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
    explainability = explainability_report if isinstance(explainability_report, Mapping) else {}
    compare = decision_compare if isinstance(decision_compare, Mapping) else {}
    main_slide_checks = (
        spec.get("main_slide_checks", {})
        if isinstance(spec.get("main_slide_checks"), Mapping)
        else {}
    )
    explain_checks_raw = {
        "causal_chain_coverage": _safe_float(explainability.get("causal_chain_coverage"), default=0.0)
        >= min_causal_chain_coverage,
        "procon_cardinality_ok": bool(
            (explainability.get("checks", {}) if isinstance(explainability.get("checks"), Mapping) else {}).get(
                "procon_cardinality_ok",
                False,
            )
        ),
        "dual_alternative_integrity": (
            True
            if not decision_compare_enabled
            else bool(
                (compare.get("integrity", {}) if isinstance(compare.get("integrity"), Mapping) else {}).get(
                    "independent_optimization",
                    False,
                )
            )
        ),
        "bridge_and_sensitivity_present": bool(
            (explainability.get("checks", {}) if isinstance(explainability.get("checks"), Mapping) else {}).get(
                "bridge_and_sensitivity_present",
                False,
            )
        ),
        "main_compare_present": bool(main_slide_checks.get("main_compare_present", False)),
        "main_narrative_coverage": _safe_float(main_slide_checks.get("coverage"), default=0.0)
        >= min_main_narrative_coverage,
        "main_narrative_density_ok": bool(main_slide_checks.get("density_ok", False)),
        "decision_style_ok": bool(main_slide_checks.get("decision_style_ok", False)),
    }
    checks.update(explain_checks_raw)
    thresholds = {
        "min_numeric_trace_coverage": min_numeric_trace_coverage,
        "min_editable_shape_ratio": min_editable_shape_ratio,
        "max_runtime_seconds": max_runtime_seconds,
        "min_causal_chain_coverage": min_causal_chain_coverage,
        "min_main_narrative_coverage": min_main_narrative_coverage,
    }
    details = {
        "trace_item_count": len(trace_items),
        "traced_item_count": traced,
        "total_shape_count": total_shapes,
        "editable_shape_count": editable_shapes,
        "strict_explainability": strict_explainability,
        "decision_compare_enabled": decision_compare_enabled,
        "main_slide_checks": main_slide_checks,
    }
    base_passed = (
        checks["traceability"]
        and checks["editability"]
        and checks["runtime"]
    )
    explainability_passed = (
        checks["causal_chain_coverage"]
        and checks["procon_cardinality_ok"]
        and checks["dual_alternative_integrity"]
        and checks["bridge_and_sensitivity_present"]
        and checks["main_compare_present"]
        and checks["main_narrative_coverage"]
        and checks["main_narrative_density_ok"]
        and checks["decision_style_ok"]
    )
    return QualityGateResult(
        passed=(base_passed and explainability_passed) if strict_explainability else base_passed,
        numeric_trace_coverage=trace_coverage,
        editable_shape_ratio=editable_ratio,
        runtime_seconds=runtime_seconds,
        causal_chain_coverage=_safe_float(explainability.get("causal_chain_coverage"), default=0.0),
        procon_cardinality_ok=bool(checks["procon_cardinality_ok"]),
        dual_alternative_integrity=bool(checks["dual_alternative_integrity"]),
        bridge_and_sensitivity_present=bool(checks["bridge_and_sensitivity_present"]),
        main_compare_present=bool(checks["main_compare_present"]),
        main_narrative_coverage=_safe_float(main_slide_checks.get("coverage"), default=0.0),
        main_narrative_density_ok=bool(checks["main_narrative_density_ok"]),
        decision_style_ok=bool(checks["decision_style_ok"]),
        thresholds=thresholds,
        checks=checks,
        details=details,
    )
