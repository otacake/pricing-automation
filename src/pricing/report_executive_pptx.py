from __future__ import annotations

"""
Generate executive Markdown and PPTX deliverables from a pricing config.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import copy
import json
import os
import shutil
import subprocess
import time
from typing import Any, Mapping

import pandas as pd
import yaml

from .config import read_loading_parameters
from .diagnostics import build_execution_context, build_run_summary
from .endowment import LoadingFunctionParams, calc_loading_parameters
from .paths import resolve_base_dir_from_config
from .profit_test import DEFAULT_LAPSE_RATE, DEFAULT_VALUATION_INTEREST, run_profit_test
from .reporting import (
    DecisionAlternative,
    build_decision_alternatives,
    build_executive_deck_spec,
    build_explainability_artifacts,
    evaluate_quality_gate,
    load_style_contract,
)
from .report_feasibility import build_feasibility_report


EXPENSE_SCALE_COLUMNS = (
    "acq_var_total",
    "acq_fixed_total",
    "maint_var_total",
    "maint_fixed_total",
    "coll_var_total",
    "overhead_total",
)


@dataclass(frozen=True)
class ExecutiveReportOutputs:
    pptx_path: Path
    markdown_path: Path
    run_summary_path: Path
    feasibility_deck_path: Path
    cashflow_chart_path: Path
    premium_chart_path: Path
    spec_path: Path | None = None
    preview_html_path: Path | None = None
    quality_path: Path | None = None
    explainability_path: Path | None = None
    decision_compare_path: Path | None = None


def _resolve_output_path(base_dir: Path, path: Path | None, default: str) -> Path:
    target = Path(default) if path is None else Path(path)
    return target if target.is_absolute() else (base_dir / target)


def _require_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime env
        raise RuntimeError(
            "matplotlib is required for report-executive-pptx. "
            "Install with: python -m pip install matplotlib"
        ) from exc
    return plt


def _configure_plot_font_for_language(plt, language: str) -> None:
    if language != "ja":
        return
    try:
        from matplotlib import font_manager
    except Exception:  # pragma: no cover - defensive
        return

    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = [
        "Yu Gothic",
        "Meiryo",
        "MS Gothic",
        "Noto Sans CJK JP",
        "IPAexGothic",
    ]
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return


def _fmt_pct(value: float, digits: int = 2) -> str:
    return f"{value * 100:.{digits}f}%"


def _fmt_jpy(value: float) -> str:
    return f"JPY {value:,.0f}"


def _validate_language(language: str) -> str:
    lang = str(language).strip().lower()
    if lang not in {"ja", "en"}:
        raise ValueError(f"Unsupported language: {language}. Use 'ja' or 'en'.")
    return lang


def _validate_theme(theme: str) -> str:
    normalized = str(theme).strip().lower()
    aliases = {
        "consulting-clean": "consulting-clean-v2",
        "consulting-clean-v2": "consulting-clean-v2",
    }
    if normalized not in aliases:
        raise ValueError(
            f"Unsupported theme: {theme}. Use 'consulting-clean-v2' (or alias 'consulting-clean')."
        )
    return aliases[normalized]


def _normalize_decision_compare(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"on", "true", "1", "yes"}:
        return True
    if normalized in {"off", "false", "0", "no"}:
        return False
    raise ValueError("decision_compare must be 'on' or 'off'.")


def _require_node_runtime() -> str:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required for PptxGenJS backend but was not found in PATH.")
    return node


def _run_node_command(
    *,
    base_dir: Path,
    command: list[str],
    failure_hint: str,
) -> None:
    completed = subprocess.run(
        command,
        cwd=base_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stdout_tail = completed.stdout[-2000:]
        stderr_tail = completed.stderr[-2000:]
        raise RuntimeError(
            f"{failure_hint}\ncommand: {' '.join(command)}\nstdout_tail:\n{stdout_tail}\nstderr_tail:\n{stderr_tail}"
        )


def _scenario_label(name: str, language: str) -> str:
    if language == "en":
        return name
    mapping = {
        "base": "繝吶・繧ｹ",
        "interest_down_10pct": "驥大茜-10%",
        "interest_up_10pct": "驥大茜+10%",
        "lapse_down_10pct": "隗｣邏・紫-10%",
        "lapse_up_10pct": "隗｣邏・紫+10%",
        "expense_down_10pct": "莠区･ｭ雋ｻ-10%",
        "expense_up_10pct": "莠区･ｭ雋ｻ+10%",
    }
    return mapping.get(name, name)


def _constraint_label(name: str, language: str) -> str:
    if language == "en":
        return name
    mapping = {
        "irr_hard": "IRR荳矩剞",
        "nbv_hard": "NBV荳矩剞",
        "loading_surplus_hard": "雋闕ｷ菴吝臆荳矩剞",
        "loading_surplus_ratio_hard": "雋闕ｷ菴吝臆邇・ｸ矩剞",
        "premium_to_maturity_hard_max": "PTM荳企剞",
    }
    return mapping.get(name, name)


def _aggregate_cashflow(batch_result) -> pd.DataFrame:
    if not batch_result.results:
        raise ValueError("No model point results available.")
    frames = [res.cashflow for res in batch_result.results]
    all_cashflow = pd.concat(frames, ignore_index=True)
    agg = (
        all_cashflow.groupby("t", as_index=False)[
            [
                "premium_income",
                "investment_income",
                "death_benefit",
                "surrender_benefit",
                "expenses_total",
                "reserve_change",
                "net_cf",
            ]
        ]
        .sum()
        .sort_values("t")
    )
    agg["year"] = agg["t"].astype(int) + 1
    agg["benefit_outgo"] = -(agg["death_benefit"] + agg["surrender_benefit"])
    agg["expense_outgo"] = -agg["expenses_total"]
    agg["reserve_change_outgo"] = -agg["reserve_change"]
    return agg


def _plot_cashflow_by_profit_source(
    agg: pd.DataFrame,
    out_path: Path,
    *,
    language: str,
) -> Path:
    plt = _require_matplotlib()
    _configure_plot_font_for_language(plt, language)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    years = agg["year"].astype(int).tolist()
    if language == "ja":
        positive = [
            ("premium_income", "保険料収入", "#0b5fa5"),
            ("investment_income", "運用収益", "#2a9d8f"),
        ]
        negative = [
            ("benefit_outgo", "保険金・解約給付", "#d1495b"),
            ("expense_outgo", "予定事業費", "#f4a261"),
            ("reserve_change_outgo", "責任準備金増減", "#6c757d"),
        ]
        net_cf_label = "ネットCF"
        chart_title = "年度別キャッシュフロー（利源別・全モデルポイント合算）"
        x_label = "保険年度"
    else:
        positive = [
            ("premium_income", "Premium Income", "#0b5fa5"),
            ("investment_income", "Investment Income", "#2a9d8f"),
        ]
        negative = [
            ("benefit_outgo", "Benefit Outgo", "#d1495b"),
            ("expense_outgo", "Expense Outgo", "#f4a261"),
            ("reserve_change_outgo", "Reserve Change", "#6c757d"),
        ]
        net_cf_label = "Net CF"
        chart_title = "Yearly Cashflow by Profit Source (All Model Points)"
        x_label = "Policy Year"

    fig, ax = plt.subplots(figsize=(12, 5), dpi=150)
    pos_base = [0.0 for _ in years]
    for col, label, color in positive:
        vals = [max(float(v), 0.0) for v in agg[col].tolist()]
        ax.bar(years, vals, bottom=pos_base, label=label, color=color, width=0.8)
        pos_base = [b + v for b, v in zip(pos_base, vals)]

    neg_base = [0.0 for _ in years]
    for col, label, color in negative:
        vals = [min(float(v), 0.0) for v in agg[col].tolist()]
        ax.bar(years, vals, bottom=neg_base, label=label, color=color, width=0.8)
        neg_base = [b + v for b, v in zip(neg_base, vals)]

    ax.plot(years, agg["net_cf"], color="#111111", linewidth=2.0, label=net_cf_label)
    ax.set_title(chart_title)
    ax.set_xlabel(x_label)
    ax.set_ylabel("JPY")
    if years:
        tick_step = max(1, len(years) // 12)
        ax.set_xticks(years[::tick_step])
    ax.axhline(0.0, color="#333333", linewidth=0.8)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(ncol=3, fontsize=8, frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def _plot_annual_premium_by_model_point(
    summary_df: pd.DataFrame,
    out_path: Path,
    *,
    language: str,
) -> Path:
    plt = _require_matplotlib()
    _configure_plot_font_for_language(plt, language)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    chart_df = summary_df.sort_values("gross_annual_premium", ascending=True)
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)
    ax.barh(
        chart_df["model_point"].tolist(),
        chart_df["gross_annual_premium"].astype(float).tolist(),
        color="#0b5fa5",
    )
    if language == "ja":
        ax.set_title("モデルポイント別 年間保険料P")
        ax.set_xlabel("年間総保険料（JPY）")
    else:
        ax.set_title("Annual Premium P by Model Point")
        ax.set_xlabel("Gross Annual Premium (JPY)")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def _constraint_status_rows(run_summary: Mapping[str, Any]) -> list[dict[str, object]]:
    status_by_type: dict[str, dict[str, object]] = {}
    for model_point in run_summary["model_points"]:
        for entry in model_point["constraints"]:
            key = str(entry["type"])
            current = status_by_type.get(key)
            if current is None:
                status_by_type[key] = {
                    "constraint": key,
                    "threshold": float(entry["threshold"]),
                    "min_gap": float(entry["gap"]),
                    "worst_model_point": str(model_point["model_point"]),
                    "all_ok": bool(entry["ok"]),
                }
                continue
            gap = float(entry["gap"])
            if gap < float(current["min_gap"]):
                current["min_gap"] = gap
                current["worst_model_point"] = str(model_point["model_point"])
            if not bool(entry["ok"]):
                current["all_ok"] = False

    rows = list(status_by_type.values())
    rows.sort(key=lambda row: str(row["constraint"]))
    return rows


def _resolve_company_expense_path(config: Mapping[str, object], base_dir: Path) -> Path | None:
    profit_test_cfg = config.get("profit_test", {})
    if not isinstance(profit_test_cfg, Mapping):
        return None
    expense_cfg = profit_test_cfg.get("expense_model", {})
    if not isinstance(expense_cfg, Mapping):
        return None
    raw = expense_cfg.get("company_data_path")
    if not isinstance(raw, str):
        return None
    path = Path(raw)
    return path if path.is_absolute() else (base_dir / path)


def _scale_company_expense_file(original_path: Path, factor: float, scaled_path: Path) -> Path:
    df = pd.read_csv(original_path)
    for col in EXPENSE_SCALE_COLUMNS:
        if col in df.columns:
            scaled = df[col].astype(float) * float(factor)
            if (scaled < 0.0).any():
                raise ValueError(f"Negative planned expense assumptions are not allowed: {col}")
            df[col] = scaled
    scaled_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(scaled_path, index=False)
    return scaled_path


def _scenario_summary(name: str, config: dict, base_dir: Path) -> dict[str, object]:
    result = run_profit_test(config, base_dir=base_dir)
    summary = build_run_summary(config, result, source=f"sensitivity:{name}")
    metrics = summary["summary"]
    return {
        "scenario": name,
        "min_irr": float(metrics["min_irr"]),
        "min_nbv": float(metrics["min_nbv"]),
        "min_loading_surplus_ratio": float(metrics["min_loading_surplus_ratio"]),
        "max_premium_to_maturity": float(metrics["max_premium_to_maturity"]),
        "violation_count": int(metrics["violation_count"]),
    }


def _build_sensitivity_rows(config: dict, base_dir: Path, temp_dir: Path) -> list[dict[str, object]]:
    scenarios: list[dict[str, object]] = []
    scenarios.append(_scenario_summary("base", config, base_dir))

    pricing_cfg = config.get("pricing", {})
    if isinstance(pricing_cfg, Mapping):
        interest_cfg = pricing_cfg.get("interest", {})
        if isinstance(interest_cfg, Mapping):
            flat_rate = float(interest_cfg.get("flat_rate", 0.0))
            for factor, label in ((0.9, "interest_down_10pct"), (1.1, "interest_up_10pct")):
                scenario_cfg = copy.deepcopy(config)
                scenario_cfg["pricing"]["interest"]["flat_rate"] = flat_rate * factor
                profit_test_cfg = scenario_cfg.setdefault("profit_test", {})
                valuation = float(
                    profit_test_cfg.get("valuation_interest_rate", DEFAULT_VALUATION_INTEREST)
                )
                profit_test_cfg["valuation_interest_rate"] = valuation * factor
                scenarios.append(_scenario_summary(label, scenario_cfg, base_dir))

    lapse_base = float(
        config.get("profit_test", {}).get("lapse_rate", DEFAULT_LAPSE_RATE)
        if isinstance(config.get("profit_test", {}), Mapping)
        else DEFAULT_LAPSE_RATE
    )
    for factor, label in ((0.9, "lapse_down_10pct"), (1.1, "lapse_up_10pct")):
        scenario_cfg = copy.deepcopy(config)
        scenario_cfg.setdefault("profit_test", {})["lapse_rate"] = lapse_base * factor
        scenarios.append(_scenario_summary(label, scenario_cfg, base_dir))

    expense_path = _resolve_company_expense_path(config, base_dir)
    if expense_path is not None and expense_path.is_file():
        for factor, label in ((0.9, "expense_down_10pct"), (1.1, "expense_up_10pct")):
            scenario_cfg = copy.deepcopy(config)
            scaled = _scale_company_expense_file(
                expense_path,
                factor,
                temp_dir / f"{expense_path.stem}_{label}.csv",
            )
            scenario_cfg.setdefault("profit_test", {}).setdefault("expense_model", {})[
                "company_data_path"
            ] = str(scaled.resolve())
            scenarios.append(_scenario_summary(label, scenario_cfg, base_dir))
    return scenarios


def _get_loading_params(config: Mapping[str, object]) -> LoadingFunctionParams | None:
    return read_loading_parameters(config)


def _loading_calculation_rows(batch_result, params: LoadingFunctionParams | None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in batch_result.results:
        point = result.model_point
        age_delta = float(point.issue_age - 30)
        term_delta = float(point.term_years - 10)
        sex_indicator = 1.0 if point.sex == "female" else 0.0
        if params is None:
            alpha = float(result.loadings.alpha)
            beta = float(result.loadings.beta)
            gamma = float(result.loadings.gamma)
            alpha_expr = f"{alpha:.6f} (fixed)"
            beta_expr = f"{beta:.6f} (fixed)"
            gamma_expr = f"{gamma:.6f} (fixed)"
        else:
            generated = calc_loading_parameters(
                params=params,
                issue_age=point.issue_age,
                term_years=point.term_years,
                sex=point.sex,
            )
            alpha = float(generated.alpha)
            beta = float(generated.beta)
            gamma_raw = params.g0 + params.g_term * term_delta
            gamma = float(generated.gamma)
            alpha_expr = (
                f"{alpha:.6f} = {params.a0:.6f} + ({params.a_age:.6f}*{age_delta:.1f}) + "
                f"({params.a_term:.6f}*{term_delta:.1f}) + ({params.a_sex:.6f}*{sex_indicator:.1f})"
            )
            beta_expr = (
                f"{beta:.6f} = {params.b0:.6f} + ({params.b_age:.6f}*{age_delta:.1f}) + "
                f"({params.b_term:.6f}*{term_delta:.1f}) + ({params.b_sex:.6f}*{sex_indicator:.1f})"
            )
            gamma_expr = (
                f"{gamma:.6f} = clamp({params.g0:.6f} + ({params.g_term:.6f}*{term_delta:.1f})"
                f" = {gamma_raw:.6f}, 0.0, 0.5)"
            )
        rows.append(
            {
                "model_point": point.model_point_id,
                "sex": point.sex,
                "issue_age": point.issue_age,
                "term_years": point.term_years,
                "age_delta": age_delta,
                "term_delta": term_delta,
                "sex_indicator": sex_indicator,
                "alpha": alpha,
                "beta": beta,
                "gamma": gamma,
                "alpha_expr": alpha_expr,
                "beta_expr": beta_expr,
                "gamma_expr": gamma_expr,
            }
        )
    return rows


def _fallback_recommended_alternative(
    *,
    config: Mapping[str, Any],
    run_summary: Mapping[str, Any],
    result,
    agg_cashflow: pd.DataFrame,
    constraint_rows: list[dict[str, object]],
    sensitivity_rows: list[dict[str, object]],
) -> DecisionAlternative:
    optimization_cfg = config.get("optimization", {})
    if not isinstance(optimization_cfg, Mapping):
        optimization_cfg = {}
    objective_cfg = optimization_cfg.get("objective", {})
    if not isinstance(objective_cfg, Mapping):
        objective_cfg = {}
    objective_mode = str(objective_cfg.get("mode", "penalty"))
    metrics = run_summary.get("summary", {})
    loading_params = read_loading_parameters(config)
    params = (
        {
            "a0": float(loading_params.a0),
            "a_age": float(loading_params.a_age),
            "a_term": float(loading_params.a_term),
            "a_sex": float(loading_params.a_sex),
            "b0": float(loading_params.b0),
            "b_age": float(loading_params.b_age),
            "b_term": float(loading_params.b_term),
            "b_sex": float(loading_params.b_sex),
            "g0": float(loading_params.g0),
            "g_term": float(loading_params.g_term),
        }
        if loading_params is not None
        else {}
    )
    return DecisionAlternative(
        alternative_id="recommended",
        label="推奨案",
        objective_mode=objective_mode,
        run_summary=dict(run_summary),
        summary_df=result.summary.sort_values("model_point"),
        cashflow_df=agg_cashflow,
        constraint_rows=[dict(row) for row in constraint_rows],
        sensitivity_rows=[dict(row) for row in sensitivity_rows],
        optimized_parameters=params,
        optimization_success=True,
        optimization_iterations=0,
        metrics={
            "min_irr": float(metrics.get("min_irr", 0.0)),
            "min_nbv": float(metrics.get("min_nbv", 0.0)),
            "min_loading_surplus_ratio": float(metrics.get("min_loading_surplus_ratio", 0.0)),
            "max_premium_to_maturity": float(metrics.get("max_premium_to_maturity", 0.0)),
            "violation_count": float(metrics.get("violation_count", 0.0)),
        },
        batch_result=result,
    )


def _build_markdown_report(
    *,
    config_path: Path,
    markdown_path: Path,
    run_summary: Mapping[str, Any],
    batch_result,
    feasibility_deck: Mapping[str, Any],
    sensitivity_rows: list[dict[str, object]],
    cashflow_chart_path: Path,
    premium_chart_path: Path,
    language: str,
) -> str:
    language = _validate_language(language)
    is_ja = language == "ja"
    summary = run_summary["summary"]
    cashflow_rel = Path(os.path.relpath(cashflow_chart_path, markdown_path.parent)).as_posix()
    premium_rel = Path(os.path.relpath(premium_chart_path, markdown_path.parent)).as_posix()
    params = _get_loading_params(yaml.safe_load(config_path.read_text(encoding="utf-8")))
    loading_rows = _loading_calculation_rows(batch_result, params)
    summary_df = batch_result.summary.sort_values("model_point")
    constraint_rows = _constraint_status_rows(run_summary)

    lines: list[str] = []
    report_title = "実現可能性レポート" if is_ja else "Feasibility Report"
    generated_label = "生成日" if is_ja else "generated"
    lines.append(
        f"# {report_title} ({config_path.name}, {generated_label} {datetime.now(timezone.utc).date().isoformat()})"
    )
    lines.append("")
    lines.append("## サマリー" if is_ja else "## Summary")
    if is_ja:
        lines.append(
            f"- 制約違反件数: `violation_count={summary['violation_count']}` / `{summary['model_point_count']}` モデルポイント。"
        )
        lines.append(f"- 収益性下限: `min_irr={summary['min_irr']:.6f}`。")
        lines.append(f"- NBV下限: `min_nbv={summary['min_nbv']:.2f}` JPY。")
        lines.append(
            f"- 十分性下限: `min_loading_surplus_ratio={summary['min_loading_surplus_ratio']:.6f}`。"
        )
        lines.append(
            f"- 健全性上限: `max_premium_to_maturity={summary['max_premium_to_maturity']:.6f}`。"
        )
    else:
        lines.append(
            f"- Constraint status: `violation_count={summary['violation_count']}` across `{summary['model_point_count']}` model points."
        )
        lines.append(f"- Profitability floor: `min_irr={summary['min_irr']:.6f}`.")
        lines.append(f"- NBV floor: `min_nbv={summary['min_nbv']:.2f}` JPY.")
        lines.append(
            f"- Adequacy floor: `min_loading_surplus_ratio={summary['min_loading_surplus_ratio']:.6f}`."
        )
        lines.append(
            f"- Soundness ceiling: `max_premium_to_maturity={summary['max_premium_to_maturity']:.6f}`."
        )

    lines.append("")
    lines.append("## プライシング提案（モデルポイント別P）" if is_ja else "## Pricing Recommendation (P by Model Point)")
    lines.append("|model_point|gross_annual_premium|monthly_premium|irr|nbv|premium_to_maturity|")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in summary_df.itertuples(index=False):
        lines.append(
            f"|{row.model_point}|{int(row.gross_annual_premium)}|{int(row.monthly_premium)}|"
            f"{row.irr:.6f}|{row.new_business_value:.2f}|{row.premium_to_maturity_ratio:.6f}|"
        )

    lines.append("")
    lines.append("## 制約ステータス" if is_ja else "## Constraint Status")
    lines.append("|constraint|min_gap|worst_model_point|status|")
    lines.append("|---|---:|---|---|")
    for row in constraint_rows:
        status = "適合" if (is_ja and bool(row["all_ok"])) else "要対応" if is_ja else "PASS" if bool(row["all_ok"]) else "FAIL"
        lines.append(
            f"|{_constraint_label(str(row['constraint']), language)}|{float(row['min_gap']):.6f}|{row['worst_model_point']}|{status}|"
        )

    lines.append("")
    lines.append("## Loading式と係数" if is_ja else "## Loading Formula and Coefficients")
    lines.append("- `gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)`")
    if params is None:
        lines.append(
            "- loadingモード: 固定 `loading_alpha_beta_gamma`。"
            if is_ja
            else "- Loading mode: fixed `loading_alpha_beta_gamma`."
        )
    else:
        lines.append("- loadingモード: `loading_parameters`。" if is_ja else "- Loading mode: `loading_parameters`.")
        lines.append("|coefficient|value|")
        lines.append("|---|---:|")
        for key in ("a0", "a_age", "a_term", "a_sex", "b0", "b_age", "b_term", "b_sex", "g0", "g_term"):
            lines.append(f"|{key}|{getattr(params, key):.6f}|")

    lines.append("")
    lines.append(
        "## モデルポイント別 alpha/beta/gamma 計算（中間計算付き）"
        if is_ja
        else "## Per-model-point alpha/beta/gamma Calculations (with intermediate steps)"
    )
    for row in loading_rows:
        lines.append(
            f"### {row['model_point']} (age={row['issue_age']}, term={row['term_years']}, sex={row['sex']})"
        )
        if is_ja:
            lines.append(
                f"- 差分: `age_delta={row['age_delta']:.1f}`, `term_delta={row['term_delta']:.1f}`, `sex_indicator={row['sex_indicator']:.1f}`"
            )
        else:
            lines.append(
                f"- deltas: `age_delta={row['age_delta']:.1f}`, `term_delta={row['term_delta']:.1f}`, `sex_indicator={row['sex_indicator']:.1f}`"
            )
        lines.append(f"- alpha: `{row['alpha_expr']}`")
        lines.append(f"- beta: `{row['beta_expr']}`")
        lines.append(f"- gamma: `{row['gamma_expr']}`")

    lines.append("")
    lines.append("## 年度別キャッシュフロー（利源別）" if is_ja else "## Yearly Cashflow by Profit Source")
    lines.append(
        f"![{'年度別キャッシュフロー（利源別）' if is_ja else 'Yearly Cashflow by Profit Source'}]({cashflow_rel})"
    )
    lines.append("")
    lines.append(
        f"![{'モデルポイント別 年間保険料' if is_ja else 'Annual Premium by Model Point'}]({premium_rel})"
    )

    lines.append("")
    lines.append("## 感応度サマリー" if is_ja else "## Sensitivity Summary")
    lines.append("|scenario|min_irr|min_nbv|min_loading_surplus_ratio|max_premium_to_maturity|violation_count|")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in sensitivity_rows:
        lines.append(
            f"|{_scenario_label(str(row['scenario']), language)}|{float(row['min_irr']):.6f}|{float(row['min_nbv']):.2f}|"
            f"{float(row['min_loading_surplus_ratio']):.6f}|{float(row['max_premium_to_maturity']):.6f}|"
            f"{int(row['violation_count'])}|"
        )

    lines.append("")
    lines.append("## Feasibility Deck メタ情報" if is_ja else "## Feasibility Deck Meta")
    scan = feasibility_deck["meta"]["scan"]
    lines.append(
        f"- sweep range: `r_start={scan['r_start']}`, `r_end={scan['r_end']}`, `r_step={scan['r_step']}`, `irr_threshold={scan['irr_threshold']}`"
    )

    lines.append("")
    lines.append("## 再現コマンド" if is_ja else "## Reproducibility")
    lines.append("```powershell")
    lines.append("python -m pytest -q")
    lines.append(f"python -m pricing.cli run {config_path.as_posix()}")
    lines.append(
        "python -m pricing.cli report-feasibility "
        f"{config_path.as_posix()} --r-start 1.00 --r-end 1.08 --r-step 0.005 --irr-threshold 0.02 "
        "--out out/feasibility_deck_executive.yaml"
    )
    lines.append(
        "python -m pricing.cli report-executive-pptx "
        f"{config_path.as_posix()} --out reports/executive_pricing_deck.pptx "
        f"--md-out reports/feasibility_report.md --lang {language}"
    )
    lines.append("```")
    return "\n".join(lines)


def _write_executive_pptx_pptxgenjs(
    *,
    base_dir: Path,
    out_path: Path,
    spec_output: Path,
    preview_output: Path,
    quality_output: Path,
    style_contract_path: Path,
    theme: str,
    strict_quality: bool,
    config: Mapping[str, Any],
    run_summary: Mapping[str, Any],
    summary_df: pd.DataFrame,
    agg_cashflow: pd.DataFrame,
    constraint_rows: list[dict[str, object]],
    sensitivity_rows: list[dict[str, object]],
    config_path: Path,
    language: str,
    chart_language: str,
    alternatives_payload: Mapping[str, Any] | None,
    decision_compare: Mapping[str, Any] | None,
    explainability_report: Mapping[str, Any] | None,
    explainability_strict: bool,
    decision_compare_enabled: bool,
) -> tuple[Path, Path, Path]:
    node = _require_node_runtime()
    theme_name = _validate_theme(theme)
    contract = load_style_contract(style_contract_path)
    spec = build_executive_deck_spec(
        config=config,
        config_path=config_path,
        run_summary=run_summary,
        summary_df=summary_df,
        cashflow_df=agg_cashflow,
        constraint_rows=constraint_rows,
        sensitivity_rows=sensitivity_rows,
        style_contract=contract,
        language=language,
        chart_language=chart_language,
        theme=theme_name,
        alternatives=alternatives_payload,
        decision_compare=decision_compare,
        explainability_report=explainability_report,
    )

    spec_output.parent.mkdir(parents=True, exist_ok=True)
    spec_output.write_text(json.dumps(spec, indent=2, ensure_ascii=True), encoding="utf-8")

    tool_dir = base_dir / "tools" / "exec_deck_hybrid"
    preview_script = tool_dir / "src" / "render_preview.mjs"
    pptx_script = tool_dir / "src" / "render_pptx.mjs"
    template_path = tool_dir / "templates" / theme_name / "deck.html"
    css_path = tool_dir / "templates" / theme_name / "theme.css"

    required_paths = [preview_script, pptx_script, template_path, css_path]
    missing = [path for path in required_paths if not path.is_file()]
    if missing:
        joined = ", ".join(path.as_posix() for path in missing)
        raise RuntimeError(f"PptxGenJS renderer files are missing: {joined}")

    if not (tool_dir / "node_modules" / "pptxgenjs").exists():
        raise RuntimeError(
            "PptxGenJS backend requires Node dependencies. "
            f"Run: npm --prefix {tool_dir.as_posix()} install"
        )

    preview_output.parent.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    quality_output.parent.mkdir(parents=True, exist_ok=True)

    render_metrics_path = quality_output.with_name(f"{quality_output.stem}.render_metrics.json")
    start = time.perf_counter()
    _run_node_command(
        base_dir=base_dir,
        command=[
            node,
            str(preview_script),
            "--spec",
            str(spec_output),
            "--template",
            str(template_path),
            "--css",
            str(css_path),
            "--out",
            str(preview_output),
        ],
        failure_hint="Failed to render HTML preview for executive deck.",
    )
    _run_node_command(
        base_dir=base_dir,
        command=[
            node,
            str(pptx_script),
            "--spec",
            str(spec_output),
            "--out",
            str(out_path),
            "--metrics-out",
            str(render_metrics_path),
        ],
        failure_hint="Failed to render PPTX with PptxGenJS backend.",
    )
    runtime_seconds = time.perf_counter() - start

    render_metrics: dict[str, Any] = {}
    if render_metrics_path.is_file():
        render_metrics = json.loads(render_metrics_path.read_text(encoding="utf-8"))
    quality = evaluate_quality_gate(
        spec=spec,
        render_metrics=render_metrics,
        runtime_seconds=runtime_seconds,
        explainability_report=explainability_report,
        decision_compare=decision_compare,
        strict_explainability=bool(explainability_strict),
        decision_compare_enabled=bool(decision_compare_enabled),
    )
    quality_output.write_text(json.dumps(quality.to_dict(), indent=2, ensure_ascii=True), encoding="utf-8")
    if (strict_quality or explainability_strict) and not quality.passed:
        failed_checks = [name for name, ok in quality.checks.items() if not ok]
        failed_checks_text = ", ".join(failed_checks) if failed_checks else "unknown"
        raise RuntimeError(
            "PptxGenJS quality gate failed. "
            f"failed_checks=[{failed_checks_text}]. "
            f"See details at: {quality_output.as_posix()}"
        )
    return spec_output, preview_output, quality_output


def report_executive_pptx_from_config(
    config_path: Path,
    *,
    out_path: Path | None = None,
    markdown_path: Path | None = None,
    run_summary_path: Path | None = None,
    deck_out_path: Path | None = None,
    chart_dir: Path | None = None,
    r_start: float = 1.0,
    r_end: float = 1.08,
    r_step: float = 0.005,
    irr_threshold: float = 0.02,
    include_sensitivity: bool = True,
    language: str = "ja",
    chart_language: str = "en",
    theme: str = "consulting-clean-v2",
    style_contract_path: Path | None = None,
    spec_out_path: Path | None = None,
    preview_html_path: Path | None = None,
    quality_out_path: Path | None = None,
    strict_quality: bool = True,
    decision_compare: str | bool = "on",
    counter_objective: str = "maximize_min_irr",
    explainability_strict: bool = True,
    explain_out_path: Path | None = None,
    compare_out_path: Path | None = None,
    procon_quant_count: int = 3,
    procon_qual_count: int = 3,
    require_causal_bridge: bool = True,
    require_sensitivity_decomp: bool = True,
) -> ExecutiveReportOutputs:
    language = _validate_language(language)
    chart_language = _validate_language(chart_language)
    theme = _validate_theme(theme)
    decision_compare_enabled = _normalize_decision_compare(decision_compare)
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    base_dir = resolve_base_dir_from_config(config_path)

    result = run_profit_test(config, base_dir=base_dir)
    execution_context = build_execution_context(
        config=config,
        base_dir=base_dir,
        config_path=config_path,
        command="pricing.cli report-executive-pptx",
        argv=[
            str(config_path),
            "--theme",
            theme,
            "--lang",
            language,
            "--chart-lang",
            chart_language,
            "--decision-compare",
            "on" if decision_compare_enabled else "off",
            "--counter-objective",
            str(counter_objective),
        ],
    )
    baseline_run_summary = build_run_summary(
        config,
        result,
        source="report_executive_pptx",
        execution_context=execution_context,
    )
    baseline_agg_cashflow = _aggregate_cashflow(result)
    baseline_constraint_rows = _constraint_status_rows(baseline_run_summary)

    counter_alternative: DecisionAlternative | None = None
    if decision_compare_enabled:
        recommended_alternative, counter_alternative = build_decision_alternatives(
            config=config,
            base_dir=base_dir,
            execution_context=execution_context,
            counter_objective=str(counter_objective),
            include_sensitivity=bool(include_sensitivity),
            language=language,
        )
    else:
        baseline_sensitivity_rows = (
            _build_sensitivity_rows(
                config,
                base_dir,
                base_dir / "out" / "charts" / "executive" / "sensitivity",
            )
            if include_sensitivity
            else [_scenario_summary("base", config, base_dir)]
        )
        recommended_alternative = _fallback_recommended_alternative(
            config=config,
            run_summary=baseline_run_summary,
            result=result,
            agg_cashflow=baseline_agg_cashflow,
            constraint_rows=baseline_constraint_rows,
            sensitivity_rows=baseline_sensitivity_rows,
        )

    run_summary = recommended_alternative.run_summary
    result = recommended_alternative.batch_result
    agg_cashflow = recommended_alternative.cashflow_df
    sensitivity_rows = recommended_alternative.sensitivity_rows
    constraint_rows = recommended_alternative.constraint_rows

    run_summary_output = _resolve_output_path(
        base_dir,
        run_summary_path,
        "out/run_summary_executive.json",
    )
    run_summary_output.parent.mkdir(parents=True, exist_ok=True)
    run_summary_output.write_text(
        json.dumps(run_summary, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    effective_require_sensitivity = bool(require_sensitivity_decomp and include_sensitivity)
    explainability_report, decision_compare_payload = build_explainability_artifacts(
        config=config,
        config_path=config_path,
        run_summary_source_path=run_summary_output.as_posix(),
        recommended=recommended_alternative,
        counter=counter_alternative,
        quant_count=int(procon_quant_count),
        qual_count=int(procon_qual_count),
        require_causal_bridge=bool(require_causal_bridge),
        require_sensitivity_decomp=effective_require_sensitivity,
        language=language,
    )
    explainability_output = _resolve_output_path(
        base_dir,
        explain_out_path,
        "out/explainability_report.json",
    )
    decision_compare_output = _resolve_output_path(
        base_dir,
        compare_out_path,
        "out/decision_compare.json",
    )
    explainability_output.parent.mkdir(parents=True, exist_ok=True)
    decision_compare_output.parent.mkdir(parents=True, exist_ok=True)
    explainability_output.write_text(
        json.dumps(explainability_report, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    decision_compare_output.write_text(
        json.dumps(decision_compare_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    alternatives_payload: dict[str, Any] = {
        "recommended": recommended_alternative.to_payload(),
        "counter": counter_alternative.to_payload() if counter_alternative is not None else None,
    }

    deck = build_feasibility_report(
        config=config,
        base_dir=base_dir,
        r_start=float(r_start),
        r_end=float(r_end),
        r_step=float(r_step),
        irr_threshold=float(irr_threshold),
        config_path=config_path,
    )
    deck_output = _resolve_output_path(base_dir, deck_out_path, "out/feasibility_deck_executive.yaml")
    deck_output.parent.mkdir(parents=True, exist_ok=True)
    deck_output.write_text(
        yaml.safe_dump(deck, sort_keys=False),
        encoding="utf-8",
    )

    chart_output_dir = _resolve_output_path(base_dir, chart_dir, "out/charts/executive")
    chart_output_dir.mkdir(parents=True, exist_ok=True)
    cashflow_chart = _plot_cashflow_by_profit_source(
        agg_cashflow,
        chart_output_dir / "cashflow_by_profit_source.png",
        language=chart_language,
    )
    premium_chart = _plot_annual_premium_by_model_point(
        result.summary,
        chart_output_dir / "annual_premium_by_model_point.png",
        language=chart_language,
    )

    markdown_output = _resolve_output_path(base_dir, markdown_path, "reports/feasibility_report.md")
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(
        _build_markdown_report(
            config_path=config_path,
            markdown_path=markdown_output,
            run_summary=run_summary,
            batch_result=result,
            feasibility_deck=deck,
            sensitivity_rows=sensitivity_rows,
            cashflow_chart_path=cashflow_chart,
            premium_chart_path=premium_chart,
            language=language,
        ),
        encoding="utf-8",
    )

    pptx_output = _resolve_output_path(base_dir, out_path, "reports/executive_pricing_deck.pptx")
    spec_output: Path | None = None
    preview_output: Path | None = None
    quality_output: Path | None = None
    contract_path = _resolve_output_path(
        base_dir,
        style_contract_path,
        "docs/deck_style_contract.md",
    )
    spec_output = _resolve_output_path(
        base_dir,
        spec_out_path,
        "out/executive_deck_spec.json",
    )
    preview_output = _resolve_output_path(
        base_dir,
        preview_html_path,
        "reports/executive_pricing_deck_preview.html",
    )
    quality_output = _resolve_output_path(
        base_dir,
        quality_out_path,
        "out/executive_deck_quality.json",
    )
    _write_executive_pptx_pptxgenjs(
        base_dir=base_dir,
        out_path=pptx_output,
        spec_output=spec_output,
        preview_output=preview_output,
        quality_output=quality_output,
        style_contract_path=contract_path,
        theme=theme,
        strict_quality=bool(strict_quality),
        config=config,
        run_summary=run_summary,
        summary_df=result.summary.sort_values("model_point"),
        agg_cashflow=agg_cashflow,
        constraint_rows=constraint_rows,
        sensitivity_rows=sensitivity_rows,
        config_path=config_path,
        language=language,
        chart_language=chart_language,
        alternatives_payload=alternatives_payload,
        decision_compare=decision_compare_payload,
        explainability_report=explainability_report,
        explainability_strict=bool(explainability_strict),
        decision_compare_enabled=bool(decision_compare_enabled),
    )

    return ExecutiveReportOutputs(
        pptx_path=pptx_output,
        markdown_path=markdown_output,
        run_summary_path=run_summary_output,
        feasibility_deck_path=deck_output,
        cashflow_chart_path=cashflow_chart,
        premium_chart_path=premium_chart,
        spec_path=spec_output,
        preview_html_path=preview_output,
        quality_path=quality_output,
        explainability_path=explainability_output,
        decision_compare_path=decision_compare_output,
    )

