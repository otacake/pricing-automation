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
class ReportPolicy:
    generate_markdown: bool
    generate_executive_pptx: bool
    report_language: str
    chart_language: str


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
        ),
    )
