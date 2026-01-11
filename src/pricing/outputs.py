from __future__ import annotations

"""
Output helpers for profit test results.
"""

from pathlib import Path

from openpyxl import Workbook

from .profit_test import ProfitTestResult


def write_profit_test_excel(path: Path, result: ProfitTestResult) -> Path:
    """
    Write profit test results to an Excel workbook.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "profit_test"

    ws["A1"] = "IRR"
    ws["B1"] = result.irr
    ws["A3"] = "New business value"
    ws["C3"] = result.new_business_value

    headers = list(result.cashflow.columns)
    header_row = 4
    data_row_start = header_row + 1
    for col_idx, name in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=name)

    for row_offset, row in enumerate(result.cashflow.itertuples(index=False), start=0):
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=data_row_start + row_offset, column=col_idx, value=value)

    wb.save(path)
    return path


def write_profit_test_log(
    path: Path, config: dict, result: ProfitTestResult
) -> Path:
    """
    Write a plain-text log with key assumptions and outputs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    product = config["product"]
    model_point = config["model_point"]
    pricing = config["pricing"]
    loadings = config["loading_alpha_beta_gamma"]
    profit_test_cfg = config.get("profit_test", {})

    lines = [
        "profit_test",
        f"issue_age: {model_point['issue_age']}",
        f"sex: {model_point['sex']}",
        f"term_years: {product['term_years']}",
        f"premium_paying_years: {product['premium_paying_years']}",
        f"sum_assured: {product['sum_assured']}",
        f"pricing_interest_rate: {pricing['interest']['flat_rate']}",
        f"valuation_interest_rate: {profit_test_cfg.get('valuation_interest_rate', 'default')}",
        f"lapse_rate: {profit_test_cfg.get('lapse_rate', 'default')}",
        f"alpha: {loadings['alpha']}",
        f"beta: {loadings['beta']}",
        f"gamma: {loadings['gamma']}",
        f"net_annual_premium: {result.premiums.net_annual_premium}",
        f"gross_annual_premium: {result.premiums.gross_annual_premium}",
        f"monthly_premium: {result.premiums.monthly_premium}",
        f"irr: {result.irr}",
        f"new_business_value: {result.new_business_value}",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
