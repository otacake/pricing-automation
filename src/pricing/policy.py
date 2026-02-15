from __future__ import annotations

"""
Policy loader for autonomous PDCA pricing cycles.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml


@dataclass(frozen=True)
class GatePolicy:
    max_violation_count: int


@dataclass(frozen=True)
class FeasibilitySweepPolicy:
    enabled: bool
    r_start: float
    r_end: float
    r_step: float
    irr_threshold: float


@dataclass(frozen=True)
class DecisionComparePolicy:
    enabled: bool
    counter_objective: str


@dataclass(frozen=True)
class ExplainabilityPolicy:
    strict_gate: bool
    procon_quant_count: int
    procon_qual_count: int
    require_causal_bridge: bool
    require_sensitivity_decomp: bool


@dataclass(frozen=True)
class ReportPolicy:
    generate_markdown: bool
    generate_executive_pptx: bool
    report_language: str
    chart_language: str
    pptx_theme: str
    style_contract_path: str
    strict_quality_gate: bool
    decision_compare: DecisionComparePolicy
    explainability: ExplainabilityPolicy


@dataclass(frozen=True)
class AutoCyclePolicy:
    gate: GatePolicy
    feasibility: FeasibilitySweepPolicy
    reporting: ReportPolicy


def _as_mapping(raw: object) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        return {}
    return raw


def load_auto_cycle_policy(path: Path) -> AutoCyclePolicy:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = _as_mapping(payload)

    gate_cfg = _as_mapping(root.get("gate"))
    feasibility_cfg = _as_mapping(root.get("feasibility"))
    reporting_cfg = _as_mapping(root.get("reporting"))

    report_language = str(reporting_cfg.get("report_language", "ja")).strip().lower()
    if report_language not in ("ja", "en"):
        raise ValueError("report_language must be 'ja' or 'en'.")

    chart_language = str(reporting_cfg.get("chart_language", "en")).strip().lower()
    if chart_language not in ("ja", "en"):
        raise ValueError("chart_language must be 'ja' or 'en'.")

    legacy_pptx_engine = reporting_cfg.get("pptx_engine")
    if legacy_pptx_engine is not None:
        normalized_engine = str(legacy_pptx_engine).strip().lower()
        if normalized_engine == "legacy":
            raise ValueError(
                "reporting.pptx_engine='legacy' is no longer supported. "
                "Remove pptx_engine or set it to 'html_hybrid'."
            )
        if normalized_engine not in ("", "html_hybrid"):
            raise ValueError("reporting.pptx_engine must be omitted or set to 'html_hybrid'.")

    pptx_theme = str(reporting_cfg.get("pptx_theme", "consulting-clean")).strip().lower()
    if pptx_theme != "consulting-clean":
        raise ValueError("pptx_theme must be 'consulting-clean'.")

    style_contract_path = str(
        reporting_cfg.get("style_contract_path", "docs/deck_style_contract.md")
    ).strip()
    if not style_contract_path:
        raise ValueError("style_contract_path must not be empty.")

    decision_compare_cfg = _as_mapping(reporting_cfg.get("decision_compare"))
    counter_objective = str(
        decision_compare_cfg.get("counter_objective", "maximize_min_irr")
    ).strip()
    if not counter_objective:
        raise ValueError("reporting.decision_compare.counter_objective must not be empty.")

    explainability_cfg = _as_mapping(reporting_cfg.get("explainability"))

    return AutoCyclePolicy(
        gate=GatePolicy(
            max_violation_count=int(gate_cfg.get("max_violation_count", 0)),
        ),
        feasibility=FeasibilitySweepPolicy(
            enabled=bool(feasibility_cfg.get("enabled", True)),
            r_start=float(feasibility_cfg.get("r_start", 1.0)),
            r_end=float(feasibility_cfg.get("r_end", 1.08)),
            r_step=float(feasibility_cfg.get("r_step", 0.005)),
            irr_threshold=float(feasibility_cfg.get("irr_threshold", 0.02)),
        ),
        reporting=ReportPolicy(
            generate_markdown=bool(reporting_cfg.get("generate_markdown", True)),
            generate_executive_pptx=bool(reporting_cfg.get("generate_executive_pptx", True)),
            report_language=report_language,
            chart_language=chart_language,
            pptx_theme=pptx_theme,
            style_contract_path=style_contract_path,
            strict_quality_gate=bool(reporting_cfg.get("strict_quality_gate", True)),
            decision_compare=DecisionComparePolicy(
                enabled=bool(decision_compare_cfg.get("enabled", True)),
                counter_objective=counter_objective,
            ),
            explainability=ExplainabilityPolicy(
                strict_gate=bool(explainability_cfg.get("strict_gate", True)),
                procon_quant_count=int(explainability_cfg.get("procon_quant_count", 3)),
                procon_qual_count=int(explainability_cfg.get("procon_qual_count", 3)),
                require_causal_bridge=bool(explainability_cfg.get("require_causal_bridge", True)),
                require_sensitivity_decomp=bool(
                    explainability_cfg.get("require_sensitivity_decomp", True)
                ),
            ),
        ),
    )
