from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ..paths import resolve_base_dir_from_config
from .management_narrative import build_main_slide_checks, build_management_narrative
from .style_contract import DeckStyleContract


def _as_float(value: object) -> float:
    return float(value)


def _as_int(value: object) -> int:
    return int(value)


def _summary_claims(
    run_summary: Mapping[str, Any],
    *,
    language: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    summary = run_summary["summary"]
    labels = {
        "ja": {
            "min_irr": "\u6700\u5c0fIRR",
            "min_nbv": "\u6700\u5c0fNBV",
            "max_premium_to_maturity": "\u6700\u5927PTM",
            "violation_count": "\u9055\u53cd\u4ef6\u6570",
        },
        "en": {
            "min_irr": "Minimum IRR",
            "min_nbv": "Minimum NBV",
            "max_premium_to_maturity": "Maximum PTM",
            "violation_count": "Violation Count",
        },
    }["ja" if language == "ja" else "en"]

    formatter = {
        "min_irr": "pct",
        "min_nbv": "currency_jpy",
        "max_premium_to_maturity": "ratio",
        "violation_count": "integer",
    }
    claims: list[dict[str, Any]] = []
    trace_map: list[dict[str, str]] = []
    for key in ("min_irr", "min_nbv", "max_premium_to_maturity", "violation_count"):
        claims.append(
            {
                "id": key,
                "label": labels[key],
                "value": _as_float(summary[key]) if key != "violation_count" else _as_int(summary[key]),
                "format": formatter[key],
            }
        )
        trace_map.append(
            {
                "claim_id": key,
                "source_file": "out/run_summary_executive.json",
                "source_path": f"$.summary.{key}",
            }
        )
    return claims, trace_map


def _pricing_rows(summary_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordered = summary_df.sort_values("model_point")
    for row in ordered.itertuples(index=False):
        rows.append(
            {
                "model_point": str(row.model_point),
                "gross_annual_premium": int(row.gross_annual_premium),
                "monthly_premium": float(row.gross_annual_premium) / 12.0,
                "irr": float(row.irr),
                "nbv": float(row.new_business_value),
                "premium_to_maturity": float(row.premium_to_maturity_ratio),
                "loading_surplus_ratio": float(getattr(row, "loading_surplus_ratio", 0.0)),
            }
        )
    return rows


def _constraint_rows(
    constraint_rows: list[dict[str, object]],
    *,
    language: str,
) -> list[dict[str, Any]]:
    labels = {
        "ja": {
            "irr_hard": "IRR\u4e0b\u9650",
            "nbv_hard": "NBV\u4e0b\u9650",
            "loading_surplus_hard": "Loading surplus\u4e0b\u9650",
            "loading_surplus_ratio_hard": "Loading surplus\u6bd4\u7387\u4e0b\u9650",
            "premium_to_maturity_hard_max": "PTM\u4e0a\u9650",
        },
        "en": {},
    }["ja" if language == "ja" else "en"]

    normalized: list[dict[str, Any]] = []
    for row in constraint_rows:
        key = str(row["constraint"])
        normalized.append(
            {
                "constraint": key,
                "label": labels.get(key, key),
                "threshold": float(row["threshold"]),
                "min_gap": float(row["min_gap"]),
                "worst_model_point": str(row["worst_model_point"]),
                "all_ok": bool(row["all_ok"]),
            }
        )
    return normalized


def _cashflow_rows(cashflow_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in cashflow_df.itertuples(index=False):
        rows.append(
            {
                "year": int(row.year),
                "premium_income": float(row.premium_income),
                "investment_income": float(row.investment_income),
                "benefit_outgo": float(row.benefit_outgo),
                "expense_outgo": float(row.expense_outgo),
                "reserve_change_outgo": float(row.reserve_change_outgo),
                "net_cf": float(row.net_cf),
            }
        )
    return rows


def _sensitivity_rows(rows: list[dict[str, object]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "scenario": str(row["scenario"]),
                "min_irr": float(row["min_irr"]),
                "min_nbv": float(row["min_nbv"]),
                "min_loading_surplus_ratio": float(row["min_loading_surplus_ratio"]),
                "max_premium_to_maturity": float(row["max_premium_to_maturity"]),
                "violation_count": int(row["violation_count"]),
            }
        )
    return normalized


def _build_pricing_philosophy(language: str) -> list[str]:
    if language == "ja":
        return [
            "\u6b63\u5f53\u6027: \u4e88\u5b9a\u4e8b\u696d\u8cbb\u3092\u73fe\u5834\u5b9f\u7e3e\u304b\u3089\u8aac\u660e\u53ef\u80fd\u306b\u63a8\u8a08\u3002",
            "\u53ce\u76ca\u6027: IRR/NBV\u306e\u5e95\u5272\u308c\u3092\u9632\u304e\u3001\u5b9a\u4fa1\u30d7\u30ec\u30df\u30a2\u30e0\u3067\u542b\u307f\u640d\u3092\u56de\u907f\u3002",
            "\u5065\u5168\u6027: PTM\u4e0a\u9650\u3068Loading surplus\u7cfb\u5236\u7d04\u306e\u4e21\u7acb\u3092\u512a\u5148\u3002",
            "\u5b9f\u52d9\u611f\u89a6: \u53d7\u6ce8\u3092\u6b62\u3081\u306a\u3044\u4fa1\u683c\u7af6\u4e89\u529b\u3068\u3001\u901a\u3059\u3079\u304d\u53ce\u76ca\u6027\u57fa\u6e96\u306e\u30d0\u30e9\u30f3\u30b9\u3092\u53d6\u3063\u305f\u3002",
        ]
    return [
        "Adequacy: keep expense assumptions traceable to actual company data.",
        "Profitability: protect IRR and NBV floors while avoiding underpricing.",
        "Soundness: satisfy PTM and loading-surplus constraints jointly.",
        "Pragmatism: balance quote competitiveness and governance thresholds.",
    ]


def _build_constraint_framework(language: str) -> list[str]:
    if language == "ja":
        return [
            "\u5341\u5206\u6027: loading_surplus, loading_surplus_ratio \u304c\u95be\u5024\u4ee5\u4e0a",
            "\u53ce\u76ca\u6027: IRR, NBV \u304c\u30cf\u30fc\u30c9\u5236\u7d04\u3092\u6e80\u305f\u3059",
            "\u5065\u5168\u6027: PTM \u4e0a\u9650\u3092\u9075\u5b88\u3057\u904e\u5ea6\u306a\u4fdd\u967a\u6599\u3092\u9632\u6b62",
            "\u904b\u7528: \u30a6\u30a9\u30c3\u30c1\u70b9\u306f\u76e3\u8996\u5bfe\u8c61\u3068\u3057\u3001\u514d\u9664\u70b9\u306f\u6839\u62e0\u3068\u671f\u9650\u3092\u660e\u8a18",
        ]
    return [
        "Adequacy: loading surplus and loading surplus ratio thresholds.",
        "Profitability: IRR and NBV hard constraints.",
        "Soundness: PTM cap to avoid excessive premium burden.",
        "Governance: watch/exempt points must be documented.",
    ]


def _resolve_expense_model_info(
    *,
    config: Mapping[str, Any],
    config_path: Path,
    language: str,
) -> dict[str, Any]:
    base_dir = resolve_base_dir_from_config(config_path)
    profit_test_cfg = config.get("profit_test", {})
    if not isinstance(profit_test_cfg, Mapping):
        profit_test_cfg = {}
    expense_cfg = profit_test_cfg.get("expense_model", {})
    if not isinstance(expense_cfg, Mapping):
        expense_cfg = {}

    company_path_raw = expense_cfg.get("company_data_path")
    company_path = (
        Path(company_path_raw) if isinstance(company_path_raw, str) else Path("data/company_expense.csv")
    )
    if not company_path.is_absolute():
        company_path = (base_dir / company_path).resolve()

    overhead_cfg = expense_cfg.get("overhead_split", {})
    if not isinstance(overhead_cfg, Mapping) or not overhead_cfg:
        overhead_cfg = expense_cfg.get("include_overhead_as", {})
    if not isinstance(overhead_cfg, Mapping):
        overhead_cfg = {}
    split_acq = float(overhead_cfg.get("acquisition", 0.0))
    split_maint = float(overhead_cfg.get("maintenance", 0.0))

    if language == "ja":
        formula_lines = [
            "acq_per_policy = (acq_var_total + acq_fixed_total + overhead_total * split_acq) / new_policies",
            "maint_per_policy = (maint_var_total + maint_fixed_total + overhead_total * split_maint) / inforce_avg",
            "coll_rate = coll_var_total / premium_income",
            "non_negative_rule: acq_per_policy >= 0, maint_per_policy >= 0, coll_rate >= 0",
        ]
        rationale_lines = [
            "\u4f1a\u793e\u5b9f\u7e3eCSV\u304b\u3089\u65e5\u5e38\u904b\u7528\u3067\u8aac\u660e\u53ef\u80fd\u306a\u5358\u4fa1\u30fb\u6bd4\u7387\u306b\u5206\u89e3\u3057\u3066\u63a8\u8a08\u3002",
            "\u5171\u901a\u8cbb\u306f overhead split \u3067\u7372\u5f97/\u7dad\u6301\u306b\u914d\u8cca\u3057\u3001\u5f0f\u3092\u7d4c\u55b6\u4f1a\u8b70\u3067\u76f4\u63a5\u8aac\u660e\u53ef\u80fd\u306b\u3057\u305f\u3002",
            f"\u53c2\u7167\u30d5\u30a1\u30a4\u30eb: {company_path.as_posix()}",
            f"overhead split: acquisition={split_acq:.3f}, maintenance={split_maint:.3f}",
        ]
    else:
        formula_lines = [
            "acq_per_policy = (acq_var_total + acq_fixed_total + overhead_total * split_acq) / new_policies",
            "maint_per_policy = (maint_var_total + maint_fixed_total + overhead_total * split_maint) / inforce_avg",
            "coll_rate = coll_var_total / premium_income",
            "non_negative_rule: acq_per_policy >= 0, maint_per_policy >= 0, coll_rate >= 0",
        ]
        rationale_lines = [
            "Assumptions are estimated from company actual CSV into explainable unit costs and rates.",
            "Overhead is allocated to acquisition/maintenance through explicit split factors.",
            f"source_file: {company_path.as_posix()}",
            f"overhead split: acquisition={split_acq:.3f}, maintenance={split_maint:.3f}",
        ]

    return {
        "company_data_path": company_path.as_posix(),
        "overhead_split_acquisition": split_acq,
        "overhead_split_maintenance": split_maint,
        "formula_lines": formula_lines,
        "rationale_lines": rationale_lines,
    }


def _build_cashflow_insights(rows: list[dict[str, Any]], language: str) -> list[str]:
    if not rows:
        return ["cashflow data unavailable"] if language != "ja" else ["\u30ad\u30e3\u30c3\u30b7\u30e5\u30d5\u30ed\u30fc\u30c7\u30fc\u30bf\u304c\u53d6\u5f97\u3067\u304d\u307e\u305b\u3093\u3002"]

    total_premium = sum(float(row["premium_income"]) for row in rows)
    total_investment = sum(float(row["investment_income"]) for row in rows)
    total_benefit = sum(float(row["benefit_outgo"]) for row in rows)
    total_expense = sum(float(row["expense_outgo"]) for row in rows)
    total_reserve = sum(float(row["reserve_change_outgo"]) for row in rows)
    total_net = sum(float(row["net_cf"]) for row in rows)
    inflow_total = total_premium + total_investment
    inv_ratio = (total_investment / inflow_total) if inflow_total else 0.0

    peak_year = max(rows, key=lambda row: float(row["net_cf"]))
    trough_year = min(rows, key=lambda row: float(row["net_cf"]))

    if language == "ja":
        return [
            f"\u5229\u5dee\u76ca\uff08investment income\uff09\u306f\u5165\u91d1\u5408\u8a08\u306e {inv_ratio * 100:.1f}% \u3092\u5360\u3081\u3001\u904b\u7528\u524d\u63d0\u66f4\u65b0\u306e\u5bc4\u4e0e\u304c\u78ba\u8a8d\u3067\u304d\u308b\u3002",
            f"\u7d2f\u8a08net cashflow\u306f {total_net:,.0f} JPY\uff08premium={total_premium:,.0f}, investment={total_investment:,.0f}, benefit={total_benefit:,.0f}, expense={total_expense:,.0f}, reserve={total_reserve:,.0f}\uff09\u3002",
            f"\u6700\u5927\u5e74\u6b21\u7d14CF: Y{int(peak_year['year'])} ({float(peak_year['net_cf']):,.0f} JPY)\u3001\u6700\u4f4e\u5e74\u6b21\u7d14CF: Y{int(trough_year['year'])} ({float(trough_year['net_cf']):,.0f} JPY)\u3002",
        ]
    return [
        f"Investment income represents {inv_ratio * 100:.1f}% of total inflow.",
        f"Cumulative net cashflow = {total_net:,.0f} JPY.",
        f"Peak annual net CF: Y{int(peak_year['year'])}, trough annual net CF: Y{int(trough_year['year'])}.",
    ]


def build_executive_deck_spec(
    *,
    config: Mapping[str, Any],
    config_path: Path,
    run_summary: Mapping[str, Any],
    summary_df: pd.DataFrame,
    cashflow_df: pd.DataFrame,
    constraint_rows: list[dict[str, object]],
    sensitivity_rows: list[dict[str, object]],
    style_contract: DeckStyleContract,
    language: str,
    chart_language: str,
    theme: str,
    alternatives: Mapping[str, Any] | None = None,
    decision_compare: Mapping[str, Any] | None = None,
    explainability_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    claims, trace_map = _summary_claims(run_summary, language=language)
    pricing_rows = _pricing_rows(summary_df)
    constraint_status = _constraint_rows(constraint_rows, language=language)
    cashflow_rows = _cashflow_rows(cashflow_df)
    sensitivity = _sensitivity_rows(sensitivity_rows)
    is_ja = language == "ja"

    decision_asks = (
        [
            "\u30b9\u30e9\u30a4\u30c93\u306e\u30e2\u30c7\u30eb\u30dd\u30a4\u30f3\u30c8\u5225\u4fa1\u683cP\u306e\u627f\u8a8d\u3092\u304a\u9858\u3044\u3057\u307e\u3059\u3002",
            "\u5236\u7d04\u95be\u5024\u3068\u76e3\u8996\u6761\u4ef6\u3092\u30ed\u30c3\u30af\u3057\u3001\u524d\u63d0\u66f4\u65b0\u6642\u306f\u5373\u65e5\u518d\u5b9f\u884c\u3057\u307e\u3059\u3002",
            "min_irr < 2.0% \u307e\u305f\u306f max PTM > 1.056 \u306e\u5834\u5408\u306f\u5373\u6642\u30ec\u30d3\u30e5\u30fc\u3092\u8d77\u52d5\u3057\u307e\u3059\u3002",
            "\u73fe\u5834\u3067\u8a2d\u5b9a\u53ef\u80fd\u306a\u4fa1\u683c\u7af6\u4e89\u529b\u3068\u3001\u5c06\u6765\u306e\u640d\u76ca\u3076\u308c\u8010\u6027\u3092\u4e21\u7acb\u3055\u305b\u308b\u8a2d\u8a08\u601d\u60f3\u3067\u3059\u3002",
        ]
        if is_ja
        else [
            "Approve the model-point pricing table P shown in Slide 3.",
            "Lock thresholds and rerun the package whenever assumptions change.",
            "Trigger immediate review if min_irr < 2.0% or max PTM > 1.056.",
            "The design balances quote competitiveness and downside resilience.",
        ]
    )

    headline = (
        "\u5341\u5206\u6027\u30fb\u53ce\u76ca\u6027\u30fb\u5065\u5168\u6027\u3092\u540c\u6642\u5145\u8db3\u3059\u308b\u4fa1\u683c\u63d0\u6848"
        if is_ja
        else "Pricing recommendation balancing adequacy, profitability, and soundness"
    )
    alternatives_payload = dict(alternatives) if isinstance(alternatives, Mapping) else {}
    decision_compare_payload = (
        dict(decision_compare) if isinstance(decision_compare, Mapping) else {}
    )
    explainability_payload = (
        dict(explainability_report) if isinstance(explainability_report, Mapping) else {}
    )
    slide_ids = [str(item.get("id")) for item in style_contract.frontmatter["slides"]]
    management_narrative = build_management_narrative(
        run_summary=run_summary,
        pricing_rows=pricing_rows,
        constraint_rows=constraint_status,
        cashflow_rows=cashflow_rows,
        sensitivity_rows=sensitivity,
        decision_compare=decision_compare_payload,
        explainability_report=explainability_payload,
        language=language,
    )
    main_slide_checks = build_main_slide_checks(
        management_narrative=management_narrative,
        slide_ids=slide_ids,
        narrative_contract=style_contract.frontmatter["narrative"],
        decision_compare=decision_compare_payload,
    )

    return {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "config_path": config_path.as_posix(),
            "language": language,
            "chart_language": chart_language,
            "theme": theme,
            "style_contract_path": style_contract.path.as_posix(),
        },
        "style": style_contract.to_dict(),
        "slides": style_contract.frontmatter["slides"],
        "headline": headline,
        "summary_claims": claims,
        "pricing_table": pricing_rows,
        "constraint_status": constraint_status,
        "cashflow_by_source": cashflow_rows,
        "cashflow_insights": _build_cashflow_insights(cashflow_rows, language),
        "sensitivity": sensitivity,
        "decision_asks": decision_asks,
        "pricing_philosophy": _build_pricing_philosophy(language),
        "constraint_framework": _build_constraint_framework(language),
        "expense_model": _resolve_expense_model_info(
            config=config,
            config_path=config_path,
            language=language,
        ),
        "alternatives": alternatives_payload,
        "decision_compare": decision_compare_payload,
        "procon": explainability_payload.get("procon", {}),
        "why_tree": explainability_payload.get("why_tree", {}),
        "causal_bridge": explainability_payload.get("causal_bridge", {}),
        "sensitivity_decomposition": explainability_payload.get("sensitivity_decomposition", {}),
        "formula_catalog": explainability_payload.get("formula_catalog", {}),
        "management_narrative": management_narrative,
        "main_slide_checks": main_slide_checks,
        "explainability": {
            "causal_chain_coverage": explainability_payload.get("causal_chain_coverage", 0.0),
            "checks": explainability_payload.get("checks", {}),
        },
        "trace_map": trace_map,
    }
