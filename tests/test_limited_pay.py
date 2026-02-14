from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pricing.profit_test as profit_test_mod


def test_limited_pay_keeps_coverage_cashflows(monkeypatch) -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["model_points"] = [
        {
            "id": "male_age40_term20_pay10",
            "sex": "male",
            "issue_age": 40,
            "term_years": 20,
            "premium_paying_years": 10,
            "sum_assured": 3_000_000,
        }
    ]
    config["profit_test"]["expense_model"] = {"mode": "loading"}

    monkeypatch.setattr(profit_test_mod, "calc_irr", lambda *args, **kwargs: 0.0)
    result = profit_test_mod.run_profit_test(config, base_dir=REPO_ROOT)
    cashflow = result.results[0].cashflow

    after_premium = cashflow[cashflow["t"] >= 10]
    assert float(after_premium["premium_income"].sum()) == 0.0
    assert float(after_premium["death_benefit"].sum()) > 0.0
    assert float(after_premium["surrender_benefit"].sum()) > 0.0
    assert float(after_premium["reserve_change"].abs().sum()) > 0.0
