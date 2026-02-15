from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.reporting.alternatives import DecisionAlternative
from pricing.reporting.explainability import build_explainability_artifacts


def _make_alt(
    *,
    alt_id: str,
    objective_mode: str,
    annual_premium: float,
    min_irr: float,
    min_nbv: float,
) -> DecisionAlternative:
    summary_df = pd.DataFrame(
        [
            {
                "model_point": "male_age30_term35",
                "gross_annual_premium": annual_premium,
                "irr": min_irr,
                "new_business_value": min_nbv,
                "premium_to_maturity_ratio": 1.03,
                "loading_surplus_ratio": -0.02,
            }
        ]
    )
    cashflow_df = pd.DataFrame(
        [
            {
                "year": 1,
                "premium_income": 1000.0 if alt_id == "recommended" else 900.0,
                "investment_income": 100.0 if alt_id == "recommended" else 95.0,
                "benefit_outgo": -500.0,
                "expense_outgo": -200.0,
                "reserve_change_outgo": -150.0,
                "net_cf": 250.0 if alt_id == "recommended" else 180.0,
            }
        ]
    )
    run_summary = {
        "summary": {
            "min_irr": min_irr,
            "min_nbv": min_nbv,
            "min_loading_surplus_ratio": -0.02,
            "max_premium_to_maturity": 1.03,
            "violation_count": 0,
        },
        "model_points": [],
    }
    return DecisionAlternative(
        alternative_id=alt_id,
        label=alt_id,
        objective_mode=objective_mode,
        run_summary=run_summary,
        summary_df=summary_df,
        cashflow_df=cashflow_df,
        constraint_rows=[],
        sensitivity_rows=[
            {
                "scenario": "base",
                "min_irr": min_irr,
                "min_nbv": min_nbv,
                "min_loading_surplus_ratio": -0.02,
                "max_premium_to_maturity": 1.03,
                "violation_count": 0,
            },
            {
                "scenario": "interest_down_10pct",
                "min_irr": min_irr - 0.005,
                "min_nbv": min_nbv - 1000.0,
                "min_loading_surplus_ratio": -0.03,
                "max_premium_to_maturity": 1.04,
                "violation_count": 1,
            },
        ],
        optimized_parameters={
            "a0": 0.03 if alt_id == "recommended" else 0.031,
            "a_age": 0.0,
            "a_term": 0.0,
            "a_sex": 0.0,
            "b0": 0.007,
            "b_age": 0.0,
            "b_term": 0.0,
            "b_sex": 0.0,
            "g0": 0.03,
            "g_term": 0.0,
        },
        optimization_success=True,
        optimization_iterations=10,
        metrics={
            "min_irr": min_irr,
            "min_nbv": min_nbv,
            "min_loading_surplus_ratio": -0.02,
            "max_premium_to_maturity": 1.03,
            "violation_count": 0.0,
        },
        batch_result=None,
    )


def test_build_explainability_artifacts_outputs_required_sections() -> None:
    rec = _make_alt(
        alt_id="recommended",
        objective_mode="penalty",
        annual_premium=100000.0,
        min_irr=0.03,
        min_nbv=120000.0,
    )
    ctr = _make_alt(
        alt_id="counter",
        objective_mode="maximize_min_irr",
        annual_premium=105000.0,
        min_irr=0.031,
        min_nbv=118000.0,
    )
    config = {
        "profit_test": {
            "expense_model": {
                "company_data_path": str((REPO_ROOT / "data" / "company_expense.csv").resolve())
            }
        }
    }
    explain, compare = build_explainability_artifacts(
        config=config,
        config_path=REPO_ROOT / "configs" / "trial-001.yaml",
        run_summary_source_path="out/run_summary_executive.json",
        recommended=rec,
        counter=ctr,
        quant_count=3,
        qual_count=3,
        require_causal_bridge=True,
        require_sensitivity_decomp=True,
        language="ja",
    )
    assert explain["checks"]["procon_cardinality_ok"] is True
    assert explain["checks"]["bridge_and_sensitivity_present"] is True
    assert explain["causal_chain_coverage"] == 1.0
    assert "recommended" in explain["procon"]
    assert "counter" in explain["procon"]
    assert compare["enabled"] is True
    assert compare["integrity"]["independent_optimization"] is True
