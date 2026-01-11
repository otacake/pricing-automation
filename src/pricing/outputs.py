from __future__ import annotations

"""
Output helpers for profit test results.
"""

from pathlib import Path

from openpyxl import Workbook

from .config import load_optimization_settings, loading_surplus_threshold
from .optimize import OptimizationResult
from .profit_test import ProfitTestBatchResult, ProfitTestResult, model_point_label


def _write_cashflow_sheet(ws, result: ProfitTestResult) -> None:
    headers = list(result.cashflow.columns)
    header_row = 4
    data_row_start = header_row + 1
    for col_idx, name in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=name)

    for row_offset, row in enumerate(result.cashflow.itertuples(index=False), start=0):
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=data_row_start + row_offset, column=col_idx, value=value)


def _write_summary_sheet(ws, summary) -> None:
    headers = list(summary.columns)
    for col_idx, name in enumerate(headers, start=1):
        ws.cell(row=1, column=col_idx, value=name)

    for row_idx, row in enumerate(summary.itertuples(index=False), start=2):
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)


def write_profit_test_excel(path: Path, result: ProfitTestBatchResult) -> Path:
    """
    Write profit test results to an Excel workbook.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "profit_test"

    first = result.results[0]
    ws["A1"] = "IRR"
    ws["B1"] = first.irr
    ws["A3"] = "New business value"
    ws["C3"] = first.new_business_value

    _write_cashflow_sheet(ws, first)

    summary_ws = wb.create_sheet(title="モデルポイント別サマリー")
    _write_summary_sheet(summary_ws, result.summary)

    wb.save(path)
    return path


def write_profit_test_log(
    path: Path, config: dict, result: ProfitTestBatchResult
) -> Path:
    """
    Write a plain-text log with key assumptions and outputs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    product = config["product"]
    pricing = config["pricing"]
    profit_test_cfg = config.get("profit_test", {})
    constraints_cfg = config.get("constraints", {})
    expense_sufficiency = config.get("expense_sufficiency", {})

    lines = [
        "profit_test",
        f"term_years(default): {product.get('term_years', 'n/a')}",
        f"premium_paying_years(default): {product.get('premium_paying_years', 'n/a')}",
        f"sum_assured(default): {product.get('sum_assured', 'n/a')}",
        f"pricing_interest_rate: {pricing['interest']['flat_rate']}",
        f"valuation_interest_rate: {profit_test_cfg.get('valuation_interest_rate', 'default')}",
        f"lapse_rate: {profit_test_cfg.get('lapse_rate', 'default')}",
        f"irr_min: {constraints_cfg.get('irr_min', 'n/a')}",
        f"expense_sufficiency: {expense_sufficiency.get('method', 'n/a')}",
        f"expense_sufficiency_threshold: {expense_sufficiency.get('threshold', 'n/a')}",
    ]

    if result.expense_assumptions is not None:
        lines.extend(
            [
                "expense_assumptions",
                f"expense_year: {result.expense_assumptions.year}",
                f"acq_per_policy: {result.expense_assumptions.acq_per_policy}",
                f"maint_per_policy: {result.expense_assumptions.maint_per_policy}",
                f"coll_rate: {result.expense_assumptions.coll_rate}",
            ]
        )

    lines.append("model_point_summary")
    for row in result.summary.itertuples(index=False):
        label = row.model_point if hasattr(row, "model_point") else model_point_label(
            result.results[0].model_point
        )
        line = (
            f"{label} "
            f"irr={row.irr} "
            f"nbv={row.new_business_value} "
            f"loading_surplus={row.loading_surplus} "
            f"premium_to_maturity={row.premium_to_maturity_ratio}"
        )
        lines.append(line)
        if row.premium_to_maturity_ratio > 1.0:
            # Warn when total premium exceeds maturity benefit.
            lines.append(f"warning: premium_total_exceeds_maturity {label}")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_optimize_log(
    path: Path, config: dict, result: OptimizationResult
) -> Path:
    """
    Write optimization results to a plain-text log.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    settings = load_optimization_settings(config)

    lines = [
        "optimize",
        f"irr_hard: {settings.irr_hard}",
        f"irr_target: {settings.irr_target}",
        f"loading_surplus_hard: {settings.loading_surplus_hard}",
        f"loading_surplus_hard_ratio: {settings.loading_surplus_hard_ratio}",
        f"premium_to_maturity_hard_max: {settings.premium_to_maturity_hard_max}",
        f"premium_to_maturity_target: {settings.premium_to_maturity_target}",
        f"nbv_hard: {settings.nbv_hard}",
        f"l2_lambda: {settings.l2_lambda}",
        f"success: {result.success}",
        f"iterations: {result.iterations}",
        "loading_parameters",
        f"a0: {result.params.a0}",
        f"a_age: {result.params.a_age}",
        f"a_term: {result.params.a_term}",
        f"a_sex: {result.params.a_sex}",
        f"b0: {result.params.b0}",
        f"b_age: {result.params.b_age}",
        f"b_term: {result.params.b_term}",
        f"b_sex: {result.params.b_sex}",
        f"g0: {result.params.g0}",
        f"g_term: {result.params.g_term}",
    ]

    if result.watch_model_points is not None:
        watch_ids = result.watch_model_points
        lines.append(f"watch_list: {', '.join(watch_ids) if watch_ids else 'none'}")

    if result.exempt_model_points is not None:
        exempt_ids = result.exempt_model_points
        lines.append(f"exempt_list: {', '.join(exempt_ids) if exempt_ids else 'none'}")
        if result.exemption_settings is not None:
            sweep = result.exemption_settings.sweep
            for model_id in exempt_ids:
                lines.append(
                    "exempt_detail "
                    f"id={model_id} "
                    f"start={sweep.start} "
                    f"end={sweep.end} "
                    f"step={sweep.step} "
                    f"irr_threshold={sweep.irr_threshold}"
                )

    lines.append("model_point_summary")
    for row in result.batch_result.summary.itertuples(index=False):
        label = row.model_point
        if label in result.exempt_model_points:
            lines.append(
                f"{label} status=exempt"
            )
            continue
        if label in result.watch_model_points:
            threshold = loading_surplus_threshold(settings, int(row.sum_assured))
            loading_ratio = row.loading_surplus / float(row.sum_assured)
            lines.append(
                f"{label} irr={row.irr} "
                f"nbv={row.new_business_value} "
                f"loading_surplus={row.loading_surplus} "
                f"premium_to_maturity={row.premium_to_maturity_ratio} "
                f"loading_surplus_threshold={threshold} "
                f"loading_surplus_ratio={loading_ratio} "
                f"status=watch"
            )
            if row.premium_to_maturity_ratio > 1.0:
                lines.append(f"warning: premium_total_exceeds_maturity {label}")
            continue
        threshold = loading_surplus_threshold(settings, int(row.sum_assured))
        loading_ratio = row.loading_surplus / float(row.sum_assured)
        irr_shortfall = max(settings.irr_hard - row.irr, 0.0)
        loading_shortfall = max(threshold - row.loading_surplus, 0.0)
        premium_excess = max(
            row.premium_to_maturity_ratio - settings.premium_to_maturity_hard_max, 0.0
        )
        nbv_shortfall = max(settings.nbv_hard - row.new_business_value, 0.0)
        status = (
            "pass"
            if irr_shortfall <= 0.0
            and loading_shortfall <= 0.0
            and premium_excess <= 0.0
            and nbv_shortfall <= 0.0
            else "fail"
        )
        lines.append(
            f"{label} irr={row.irr} "
            f"nbv={row.new_business_value} "
            f"loading_surplus={row.loading_surplus} "
            f"premium_to_maturity={row.premium_to_maturity_ratio} "
            f"loading_surplus_threshold={threshold} "
            f"loading_surplus_ratio={loading_ratio} "
            f"status={status}"
        )
        if status == "fail":
            if irr_shortfall > 0.0:
                lines.append(f"shortfall: irr_hard {label} {irr_shortfall:.6f}")
            if loading_shortfall > 0.0:
                lines.append(
                    f"shortfall: loading_surplus_hard {label} {loading_shortfall:.2f}"
                )
            if premium_excess > 0.0:
                lines.append(
                    f"shortfall: premium_to_maturity_hard {label} {premium_excess:.6f}"
                )
            if nbv_shortfall > 0.0:
                lines.append(f"shortfall: nbv_hard {label} {nbv_shortfall:.2f}")
        if row.premium_to_maturity_ratio > 1.0:
            # Warn when total premium exceeds maturity benefit.
            lines.append(f"warning: premium_total_exceeds_maturity {label}")

    if result.failure_details:
        lines.append("constraint_failures")
        lines.extend(result.failure_details)

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
