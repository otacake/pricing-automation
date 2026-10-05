from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.cli import main
from pricing.data_quality import validate_input_data
from pricing.validation import has_validation_errors


def _synthetic_config() -> dict:
    path = REPO_ROOT / "configs" / "trial-001.synthetic.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_synthetic_config_passes_gate_a() -> None:
    issues = validate_input_data(_synthetic_config(), REPO_ROOT)
    assert not has_validation_errors(issues)


def test_cli_validate_data_ok() -> None:
    code = main(["validate-data", str(REPO_ROOT / "configs" / "trial-001.synthetic.yaml")])
    assert code == 0


def test_negative_planned_expense_fails(tmp_path: Path) -> None:
    source = REPO_ROOT / "tests" / "fixtures" / "data" / "company_expense.csv"
    frame = pd.read_csv(source)
    frame.loc[0, "acq_var_total"] = -1
    expense_path = tmp_path / "company_expense.csv"
    frame.to_csv(expense_path, index=False)
    config = _synthetic_config()
    config["profit_test"]["expense_model"]["company_data_path"] = str(expense_path)
    issues = validate_input_data(config, REPO_ROOT)
    assert any(issue.code == "negative_planned_expense" for issue in issues)


def test_duplicate_and_null_model_point_ids_fail() -> None:
    config = _synthetic_config()
    config["model_points"][1]["id"] = config["model_points"][0]["id"]
    config["model_points"][2]["id"] = None
    issues = validate_input_data(config, REPO_ROOT)
    codes = {issue.code for issue in issues}
    assert "duplicate_model_point_id" in codes
    assert "null_model_point_id" in codes


def test_sum_assured_must_be_positive() -> None:
    config = _synthetic_config()
    config["model_points"][0]["sum_assured"] = 0
    issues = validate_input_data(config, REPO_ROOT)
    assert any(issue.code == "sum_assured_not_positive" for issue in issues)


def test_omitted_sum_assured_inherits_product_default() -> None:
    config = _synthetic_config()
    for point in config["model_points"]:
        del point["sum_assured"]
    config["product"]["sum_assured"] = 1_000_000
    issues = validate_input_data(config, REPO_ROOT)
    assert not any(issue.code == "sum_assured_not_positive" for issue in issues)


def test_omitted_sum_assured_rejects_non_positive_product_default() -> None:
    config = _synthetic_config()
    for point in config["model_points"]:
        del point["sum_assured"]
    config["product"]["sum_assured"] = 0
    issues = validate_input_data(config, REPO_ROOT)
    assert any(issue.code == "sum_assured_not_positive" for issue in issues)


def test_explicit_sum_assured_does_not_inherit_product_default() -> None:
    config = _synthetic_config()
    config["product"]["sum_assured"] = 1_000_000
    config["model_points"][0]["sum_assured"] = None
    issues = validate_input_data(config, REPO_ROOT)
    assert any(issue.code == "sum_assured_not_positive" for issue in issues)


def test_unused_model_point_is_excluded_when_model_points_is_set() -> None:
    config = _synthetic_config()
    config["model_point"] = {
        "id": None,
        "sum_assured": 0,
        "issue_age": 30,
        "sex": "male",
    }
    issues = validate_input_data(config, REPO_ROOT)
    codes = {issue.code for issue in issues}
    assert "null_model_point_id" not in codes
    assert "sum_assured_not_positive" not in codes

    config["model_point"]["id"] = config["model_points"][0]["id"]
    config["model_point"]["sum_assured"] = 1
    issues = validate_input_data(config, REPO_ROOT)
    assert not any(issue.code == "duplicate_model_point_id" for issue in issues)


def test_missing_mortality_column_fails(tmp_path: Path) -> None:
    frame = pd.read_csv(REPO_ROOT / "tests" / "fixtures" / "data" / "mortality_pricing.csv")
    frame = frame.drop(columns=["q_female"])
    path = tmp_path / "mortality_pricing.csv"
    frame.to_csv(path, index=False)
    config = _synthetic_config()
    config["pricing"]["mortality_path"] = str(path)
    issues = validate_input_data(config, REPO_ROOT)
    assert any(issue.code == "missing_column" for issue in issues)


def test_cli_validate_data_fails_on_bad_sum_assured(tmp_path: Path) -> None:
    config = _synthetic_config()
    config["model_points"][0]["sum_assured"] = -5
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    code = main(["validate-data", str(path)])
    assert code == 1
