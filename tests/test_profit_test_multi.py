from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.endowment import LoadingFunctionParams, calc_loading_parameters
from pricing.profit_test import load_company_expense_assumptions, run_profit_test


def test_company_expense_missing_raises() -> None:
    missing = REPO_ROOT / "data" / "__missing__.csv"
    with pytest.raises(ValueError):
        load_company_expense_assumptions(
            missing,
            year=None,
            overhead_split_acq=0.0,
            overhead_split_maint=0.0,
        )


def test_run_profit_test_multi_model_points_no_nan() -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    result = run_profit_test(config, base_dir=REPO_ROOT)

    assert len(result.results) == 8
    summary = result.summary
    assert not summary.isna().any().any()

    numeric = summary.select_dtypes(include=["number"])
    assert not numeric.isna().any().any()
    assert math.isfinite(float(numeric["irr"].min()))


def test_loading_function_generation() -> None:
    params = LoadingFunctionParams(
        a0=0.03,
        a_age=0.001,
        a_term=0.002,
        a_sex=0.005,
        b0=0.007,
        b_age=0.0005,
        b_term=0.0002,
        b_sex=0.001,
        g0=0.49,
        g_term=0.02,
    )
    loadings = calc_loading_parameters(params, issue_age=35, term_years=15, sex="female")

    expected_alpha = 0.03 + 0.001 * 5 + 0.002 * 5 + 0.005
    expected_beta = 0.007 + 0.0005 * 5 + 0.0002 * 5 + 0.001
    expected_gamma_raw = 0.49 + 0.02 * 5
    expected_gamma = min(max(expected_gamma_raw, 0.0), 0.5)

    assert math.isclose(loadings.alpha, expected_alpha)
    assert math.isclose(loadings.beta, expected_beta)
    assert math.isclose(loadings.gamma, expected_gamma)
