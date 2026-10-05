from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DATA = REPO_ROOT / "tests" / "fixtures" / "data"
REAL_DATA_FILES = (
    REPO_ROOT / "data" / "mortality_pricing.csv",
    REPO_ROOT / "data" / "mortality_actual.csv",
    REPO_ROOT / "data" / "spot_curve_actual.csv",
    REPO_ROOT / "data" / "company_expense.csv",
)


def real_data_available() -> bool:
    return all(path.is_file() for path in REAL_DATA_FILES)


def apply_fixture_inputs(config: dict) -> dict:
    """Point a config at tracked synthetic CSVs with the real input schema."""
    config.setdefault("pricing", {})["mortality_path"] = str(
        (FIXTURE_DATA / "mortality_pricing.csv").resolve()
    )
    profit_test = config.setdefault("profit_test", {})
    profit_test["mortality_actual_path"] = str((FIXTURE_DATA / "mortality_actual.csv").resolve())
    profit_test["discount_curve_path"] = str((FIXTURE_DATA / "spot_curve_actual.csv").resolve())
    expense = profit_test.setdefault("expense_model", {})
    if isinstance(expense, dict) and expense.get("mode", "company") != "loading":
        expense["company_data_path"] = str((FIXTURE_DATA / "company_expense.csv").resolve())
    return config
