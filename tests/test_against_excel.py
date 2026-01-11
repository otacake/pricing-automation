from __future__ import annotations

import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import openpyxl
import pytest
import yaml

from pricing.endowment import calc_endowment_premiums
from pricing.profit_test import run_profit_test

EXCEL_PATH = REPO_ROOT / "data" / "golden" / "養老保険_収益性_RORC.xlsx"


def test_bootstrap_missing_excel() -> None:
    script = REPO_ROOT / "scripts" / "bootstrap_from_excel.py"
    missing = REPO_ROOT / "data" / "golden" / "__missing__.xlsx"
    result = subprocess.run(
        [sys.executable, str(script), "--xlsx", str(missing)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert f"File not found: {missing}" in result.stderr


@dataclass(frozen=True)
class _MortalityGroup:
    header_row: int
    age_col: int
    male_col: int
    female_col: int | None


def _coerce_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _coerce_int(value: object) -> int | None:
    num = _coerce_float(value)
    if num is None:
        return None
    return int(round(num))


def _is_label(value: object, keyword: str) -> bool:
    if not isinstance(value, str):
        return False
    return keyword in value.replace(" ", "").replace("　", "")


def _find_mortality_groups(ws) -> list[_MortalityGroup]:
    groups: list[_MortalityGroup] = []
    max_rows = min(ws.max_row, 50)
    max_cols = min(ws.max_column, 30)
    for row in range(1, max_rows + 1):
        for col in range(1, max_cols + 1):
            if not _is_label(ws.cell(row, col).value, "年齢"):
                continue
            if not _is_label(ws.cell(row, col + 1).value, "男性"):
                continue
            female_col = None
            if _is_label(ws.cell(row, col + 2).value, "女性"):
                female_col = col + 2
            groups.append(_MortalityGroup(row, col, col + 1, female_col))
    return sorted(groups, key=lambda g: g.age_col)


def _extract_mortality_rows(ws, group: _MortalityGroup) -> list[dict[str, float | int | None]]:
    rows: list[dict[str, float | int | None]] = []
    start_row = group.header_row + 1
    started = False
    for row in range(start_row, ws.max_row + 1):
        male = _coerce_float(ws.cell(row, group.male_col).value)
        female = None
        if group.female_col is not None:
            female = _coerce_float(ws.cell(row, group.female_col).value)
        if male is None and female is None:
            if started:
                break
            continue
        started = True
        age = _coerce_int(ws.cell(row, group.age_col).value)
        if age is None:
            age = row - start_row
        rows.append({"age": age, "q_male": male, "q_female": female})
    return rows


def _require_int(value: object, label: str) -> int:
    parsed = _coerce_int(value)
    if parsed is None:
        raise AssertionError(f"Missing {label}")
    return parsed


def _require_float(value: object, label: str) -> float:
    parsed = _coerce_float(value)
    if parsed is None:
        raise AssertionError(f"Missing {label}")
    return parsed


def _load_workbook_or_skip():
    if not EXCEL_PATH.is_file():
        pytest.skip(f"Excel not found: {EXCEL_PATH}")
    return openpyxl.load_workbook(EXCEL_PATH, data_only=True)


def _get_sheet(wb, title: str):
    for name in wb.sheetnames:
        if name == title:
            return wb[name]
    raise KeyError(f"Worksheet {title} not found.")


def _sex_from_master(value: object) -> str:
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"male", "m", "男"}:
            return "male"
        if text in {"female", "f", "女"}:
            return "female"
    if isinstance(value, (int, float)):
        return "male" if int(round(value)) == 1 else "female"
    return "male"


def test_endowment_against_excel() -> None:
    wb = _load_workbook_or_skip()
    try:
        ws_master = _get_sheet(wb, "マスタ")
        ws_mortality = _get_sheet(wb, "死亡率")

        expected_A = _require_float(ws_master["F2"].value, "A")
        expected_a = _require_float(ws_master["F3"].value, "a")
        expected_net = _require_int(ws_master["G3"].value, "net annual premium")
        expected_gross = _require_int(ws_master["F6"].value, "gross annual premium")
        expected_monthly = _require_int(ws_master["F7"].value, "monthly premium")

        issue_age = _require_int(ws_master["C2"].value, "issue age")
        sex = _sex_from_master(ws_master["C3"].value)
        term_years = _require_int(ws_master["C4"].value, "term years")
        premium_paying_years = _require_int(ws_master["C5"].value, "premium paying years")
        sum_assured = _require_int(ws_master["C6"].value, "sum assured")
        interest_rate = _require_float(ws_master["C8"].value, "interest rate")
        alpha = _require_float(ws_master["C14"].value, "alpha")
        beta = _require_float(ws_master["C15"].value, "beta")
        gamma = _require_float(ws_master["C16"].value, "gamma")

        groups = _find_mortality_groups(ws_mortality)
        assert groups, "Mortality headers not found."
        pricing_group = groups[0]
        mortality_rows = _extract_mortality_rows(ws_mortality, pricing_group)

        premiums = calc_endowment_premiums(
            mortality_rows=mortality_rows,
            sex=sex,
            issue_age=issue_age,
            term_years=term_years,
            premium_paying_years=premium_paying_years,
            interest_rate=interest_rate,
            sum_assured=sum_assured,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
        )

        assert math.isclose(premiums.A, expected_A, abs_tol=1e-6)
        assert math.isclose(premiums.a, expected_a, abs_tol=1e-6)
        assert premiums.net_annual_premium == expected_net
        assert premiums.gross_annual_premium == expected_gross
        assert premiums.monthly_premium == expected_monthly
    finally:
        wb.close()


def test_profit_test_against_excel() -> None:
    wb = _load_workbook_or_skip()
    try:
        ws_profit = _get_sheet(wb, "収益性検証")
        expected_irr = _require_float(ws_profit["B1"].value, "IRR")
        expected_nbv = _require_float(ws_profit["C3"].value, "new business value")
    finally:
        wb.close()

    wb = _load_workbook_or_skip()
    try:
        ws_master = _get_sheet(wb, "マスタ")
        issue_age = _require_int(ws_master["C2"].value, "issue age")
        sex = _sex_from_master(ws_master["C3"].value)
        term_years = _require_int(ws_master["C4"].value, "term years")
        premium_paying_years = _require_int(ws_master["C5"].value, "premium paying years")
        sum_assured = _require_int(ws_master["C6"].value, "sum assured")
        interest_rate = _require_float(ws_master["C8"].value, "interest rate")
        alpha = _require_float(ws_master["C14"].value, "alpha")
        beta = _require_float(ws_master["C15"].value, "beta")
        gamma = _require_float(ws_master["C16"].value, "gamma")
    finally:
        wb.close()

    config = {
        "product": {
            "type": "endowment",
            "term_years": term_years,
            "premium_paying_years": premium_paying_years,
            "sum_assured": sum_assured,
            "premium_mode": "annual",
        },
        "model_point": {"issue_age": issue_age, "sex": sex},
        "pricing": {
            "interest": {"type": "flat", "flat_rate": interest_rate},
            "mortality_path": "data/mortality_pricing.csv",
        },
        "loading_alpha_beta_gamma": {"alpha": alpha, "beta": beta, "gamma": gamma},
        "profit_test": {
            "discount_curve_path": "data/spot_curve_actual.csv",
            "mortality_actual_path": "data/mortality_actual.csv",
            "expense_model": {"mode": "loading"},
        },
    }
    result = run_profit_test(config, base_dir=REPO_ROOT)
    single = result.results[0]

    assert math.isclose(single.irr, expected_irr, abs_tol=1e-9)
    assert math.isclose(single.new_business_value, expected_nbv, abs_tol=1e-6)
