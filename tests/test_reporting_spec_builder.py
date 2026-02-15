from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.reporting.spec_builder import build_executive_deck_spec
from pricing.reporting.style_contract import load_style_contract


def test_build_executive_deck_spec_claims_match_run_summary() -> None:
    run_summary = {
        "summary": {
            "min_irr": 0.031,
            "min_nbv": 12345.0,
            "max_premium_to_maturity": 1.055,
            "violation_count": 0,
        },
        "model_points": [],
    }
    summary_df = pd.DataFrame(
        [
            {
                "model_point": "male_age30_term35",
                "gross_annual_premium": 100000,
                "irr": 0.031,
                "new_business_value": 12345.0,
                "premium_to_maturity_ratio": 1.055,
                "loading_surplus_ratio": 0.01,
            }
        ]
    )
    cashflow_df = pd.DataFrame(
        [
            {
                "year": 1,
                "premium_income": 1000.0,
                "investment_income": 100.0,
                "benefit_outgo": -300.0,
                "expense_outgo": -200.0,
                "reserve_change_outgo": -400.0,
                "net_cf": 200.0,
            }
        ]
    )
    style = load_style_contract(REPO_ROOT / "docs" / "deck_style_contract.md")
    spec = build_executive_deck_spec(
        config={},
        config_path=REPO_ROOT / "configs" / "trial-001.yaml",
        run_summary=run_summary,
        summary_df=summary_df,
        cashflow_df=cashflow_df,
        constraint_rows=[],
        sensitivity_rows=[],
        style_contract=style,
        language="ja",
        chart_language="en",
        theme="consulting-clean",
    )

    claims = {item["id"]: item["value"] for item in spec["summary_claims"]}
    assert claims["min_irr"] == run_summary["summary"]["min_irr"]
    assert claims["min_nbv"] == run_summary["summary"]["min_nbv"]
    assert claims["max_premium_to_maturity"] == run_summary["summary"]["max_premium_to_maturity"]
    assert claims["violation_count"] == run_summary["summary"]["violation_count"]
    assert "management_narrative" in spec
    assert "executive_summary" in spec["management_narrative"]
    assert "decision_statement" in spec["management_narrative"]
    assert spec["main_slide_checks"]["coverage"] >= 1.0
    assert spec["main_slide_checks"]["density_ok"] is True
