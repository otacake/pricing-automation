from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.reporting.management_narrative import (  # noqa: E402
    build_main_slide_checks,
    build_management_narrative,
)


def test_build_management_narrative_contains_required_sections() -> None:
    narrative = build_management_narrative(
        run_summary={
            "summary": {
                "min_irr": 0.025,
                "min_nbv": 120000.0,
                "max_premium_to_maturity": 1.05,
                "violation_count": 0,
            }
        },
        pricing_rows=[{"model_point": "m1", "gross_annual_premium": 100000.0}],
        constraint_rows=[{"constraint": "irr_hard", "label": "IRR下限", "min_gap": 0.003}],
        cashflow_rows=[
            {
                "year": 1,
                "premium_income": 100000.0,
                "investment_income": 10000.0,
                "benefit_outgo": -30000.0,
                "expense_outgo": -15000.0,
                "reserve_change_outgo": -40000.0,
                "net_cf": 25000.0,
            }
        ],
        sensitivity_rows=[
            {"scenario": "base", "min_irr": 0.025, "max_premium_to_maturity": 1.05, "violation_count": 0},
            {"scenario": "interest_down_10pct", "min_irr": 0.020, "max_premium_to_maturity": 1.056, "violation_count": 1},
        ],
        decision_compare={
            "enabled": True,
            "objectives": {"recommended": "base", "counter": "maximize_min_irr"},
            "metric_diff_recommended_minus_counter": {"min_irr": 0.001},
            "adoption_reason": ["理由1", "理由2"],
            "integrity": {"independent_optimization": True},
        },
        explainability_report={
            "causal_bridge": {
                "components": [
                    {"label": "保険料収入", "delta_recommended_minus_counter": 1000.0},
                    {"label": "利差益", "delta_recommended_minus_counter": 500.0},
                ]
            },
            "sensitivity_decomposition": {"recommended": [{"scenario": "interest_down_10pct"}]},
            "formula_catalog": {"planned_expense": {"source": {"path": "data/company_expense.csv"}}},
        },
        language="ja",
    )
    assert "decision_statement" in narrative
    block = narrative["decision_statement"]
    assert str(block["conclusion"]).strip()
    assert len(block["rationale"]) >= 3
    assert len(block["risk"]) >= 1
    assert len(block["decision_ask"]) >= 1


def test_build_main_slide_checks_detects_compare_and_density() -> None:
    narrative = {
        "executive_summary": {
            "section_order": ["conclusion", "rationale", "risk", "decision_ask"],
            "conclusion": "ok",
            "rationale": ["r1", "r2", "r3"],
            "risk": ["k1"],
            "decision_ask": ["a1"],
        },
        "decision_statement": {
            "section_order": ["conclusion", "rationale", "risk", "decision_ask"],
            "conclusion": "推奨案と対向案を比較して決定する。",
            "rationale": ["r1", "r2", "r3"],
            "risk": ["k1"],
            "decision_ask": ["a1"],
        },
    }
    checks = build_main_slide_checks(
        management_narrative=narrative,
        slide_ids=["executive_summary", "decision_statement"],
        narrative_contract={
            "mode": "conclusion_first",
            "comparison_layout": "dedicated_main_slide",
            "min_lines_per_main_slide": 6,
            "required_sections": ["conclusion", "rationale", "risk", "decision_ask"],
            "main_compare_slide_id": "decision_statement",
        },
        decision_compare={"enabled": True},
    )
    assert checks["coverage"] == 1.0
    assert checks["density_ok"] is True
    assert checks["main_compare_present"] is True
    assert checks["decision_style_ok"] is True
