from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.validation import (  # noqa: E402
    format_validation_issues,
    has_validation_errors,
    validate_config,
)


def _base_config() -> dict:
    return {
        "product": {"type": "endowment"},
        "model_points": [
            {
                "id": "male_age30_term20",
                "sex": "male",
                "issue_age": 30,
                "term_years": 20,
                "premium_paying_years": 20,
                "sum_assured": 1_000_000,
            }
        ],
        "pricing": {
            "interest": {"type": "flat", "flat_rate": 0.01},
            "mortality_path": "data/mortality_pricing.csv",
            "lapse": {"annual_rate": 0.0},
        },
        "profit_test": {
            "lapse_rate": 0.03,
            "discount_curve_path": "data/spot_curve_actual.csv",
            "mortality_actual_path": "data/mortality_actual.csv",
            "expense_model": {"mode": "company"},
        },
    }


def test_validate_config_warns_for_deprecated_and_ambiguous_settings() -> None:
    config = _base_config()
    config["profit_test"]["expense_model"]["include_overhead_as"] = {
        "acquisition": 0.5,
        "maintenance": 0.5,
    }
    config["typo_top"] = {}

    issues = validate_config(config)
    codes = {issue.code for issue in issues}

    assert "deprecated_key_used" in codes
    assert "ambiguous_lapse_setting" in codes
    assert "unknown_top_level_key" in codes
    assert not has_validation_errors(issues)


def test_validate_config_reports_interest_type_error() -> None:
    config = _base_config()
    config["pricing"]["interest"]["type"] = "curve"

    issues = validate_config(config)
    assert has_validation_errors(issues)
    assert any(issue.code == "unsupported_interest_type" for issue in issues)


def test_validate_config_reports_negative_overhead_split_error() -> None:
    config = _base_config()
    config["profit_test"]["expense_model"]["overhead_split"] = {
        "acquisition": -0.1,
        "maintenance": 1.0,
    }

    issues = validate_config(config)
    assert has_validation_errors(issues)
    assert any(issue.code == "negative_overhead_split" for issue in issues)
    assert any(issue.code == "overhead_split_not_unit" for issue in issues)


def test_validate_config_reports_duplicate_model_point_id_error() -> None:
    config = _base_config()
    config["model_point"] = {
        "sex": "male",
        "issue_age": 30,
        "term_years": 20,
        "premium_paying_years": 20,
        "sum_assured": 1_000_000,
    }
    config["model_points"].append(
        {
            "id": "male_age30_term20",
            "sex": "female",
            "issue_age": 30,
            "term_years": 20,
            "premium_paying_years": 20,
            "sum_assured": 1_000_000,
        }
    )

    issues = validate_config(config)
    assert has_validation_errors(issues)
    assert any(issue.code == "duplicate_model_point_id" for issue in issues)
    assert any(issue.code == "duplicated_model_point_definition" for issue in issues)


def test_format_validation_issues_contains_prefix() -> None:
    config = _base_config()
    config["typo_top"] = {}
    lines = format_validation_issues(validate_config(config), prefix="pricing.cli run")
    assert lines
    assert all(line.startswith("pricing.cli run:") for line in lines)
