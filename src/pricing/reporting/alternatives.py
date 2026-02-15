from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ..diagnostics import build_run_summary
from ..optimize import optimize_loading_parameters
from ..profit_test import DEFAULT_LAPSE_RATE, DEFAULT_VALUATION_INTEREST, run_profit_test


EXPENSE_SCALE_COLUMNS = (
    "acq_var_total",
    "acq_fixed_total",
    "maint_var_total",
    "maint_fixed_total",
    "coll_var_total",
    "overhead_total",
)


@dataclass(frozen=True)
class DecisionAlternative:
    alternative_id: str
    label: str
    objective_mode: str
    run_summary: dict[str, Any]
    summary_df: pd.DataFrame
    cashflow_df: pd.DataFrame
    constraint_rows: list[dict[str, Any]]
    sensitivity_rows: list[dict[str, Any]]
    optimized_parameters: dict[str, float]
    optimization_success: bool
    optimization_iterations: int
    metrics: dict[str, float]
    batch_result: Any

    def to_payload(self) -> dict[str, Any]:
        return {
            "alternative_id": self.alternative_id,
            "label": self.label,
            "objective_mode": self.objective_mode,
            "optimization_success": self.optimization_success,
            "optimization_iterations": self.optimization_iterations,
            "optimized_parameters": self.optimized_parameters,
            "metrics": self.metrics,
            "pricing_table": _pricing_rows(self.summary_df),
            "constraint_status": self.constraint_rows,
        }


def _as_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _objective_mode(config: Mapping[str, Any]) -> str:
    optimization_cfg = _as_mapping(config.get("optimization"))
    objective_cfg = _as_mapping(optimization_cfg.get("objective"))
    mode = objective_cfg.get("mode", "penalty")
    return str(mode)


def _with_objective_mode(config: Mapping[str, Any], objective_mode: str) -> dict[str, Any]:
    payload = copy.deepcopy(dict(config))
    optimization_cfg = payload.setdefault("optimization", {})
    if not isinstance(optimization_cfg, dict):
        optimization_cfg = {}
        payload["optimization"] = optimization_cfg
    objective_cfg = optimization_cfg.setdefault("objective", {})
    if not isinstance(objective_cfg, dict):
        objective_cfg = {}
        optimization_cfg["objective"] = objective_cfg
    objective_cfg["mode"] = objective_mode
    return payload


def _constraint_status_rows(run_summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    status_by_type: dict[str, dict[str, Any]] = {}
    for model_point in run_summary.get("model_points", []):
        if not isinstance(model_point, Mapping):
            continue
        constraints = model_point.get("constraints", [])
        if not isinstance(constraints, list):
            continue
        model_point_id = str(model_point.get("model_point", ""))
        for entry in constraints:
            if not isinstance(entry, Mapping):
                continue
            key = str(entry.get("type", ""))
            if not key:
                continue
            gap = float(entry.get("gap", 0.0))
            current = status_by_type.get(key)
            if current is None:
                status_by_type[key] = {
                    "constraint": key,
                    "threshold": float(entry.get("threshold", 0.0)),
                    "min_gap": gap,
                    "worst_model_point": model_point_id,
                    "all_ok": bool(entry.get("ok", False)),
                }
                continue
            if gap < float(current["min_gap"]):
                current["min_gap"] = gap
                current["worst_model_point"] = model_point_id
            if not bool(entry.get("ok", False)):
                current["all_ok"] = False

    rows = list(status_by_type.values())
    rows.sort(key=lambda row: str(row["constraint"]))
    return rows


def _aggregate_cashflow(batch_result: Any) -> pd.DataFrame:
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


def _resolve_company_expense_path(config: Mapping[str, Any], base_dir: Path) -> Path | None:
    profit_test_cfg = _as_mapping(config.get("profit_test"))
    expense_cfg = _as_mapping(profit_test_cfg.get("expense_model"))
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


def _scenario_summary(name: str, config: dict[str, Any], base_dir: Path) -> dict[str, Any]:
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


def _build_sensitivity_rows(config: dict[str, Any], base_dir: Path, temp_dir: Path) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    scenarios.append(_scenario_summary("base", config, base_dir))

    pricing_cfg = _as_mapping(config.get("pricing"))
    interest_cfg = _as_mapping(pricing_cfg.get("interest"))
    flat_rate = float(interest_cfg.get("flat_rate", 0.0))
    for factor, label in ((0.9, "interest_down_10pct"), (1.1, "interest_up_10pct")):
        scenario_cfg = copy.deepcopy(config)
        scenario_cfg.setdefault("pricing", {}).setdefault("interest", {})["flat_rate"] = flat_rate * factor
        profit_test_cfg = scenario_cfg.setdefault("profit_test", {})
        valuation = float(profit_test_cfg.get("valuation_interest_rate", DEFAULT_VALUATION_INTEREST))
        profit_test_cfg["valuation_interest_rate"] = valuation * factor
        scenarios.append(_scenario_summary(label, scenario_cfg, base_dir))

    lapse_base = float(_as_mapping(config.get("profit_test")).get("lapse_rate", DEFAULT_LAPSE_RATE))
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


def _build_alternative(
    *,
    alternative_id: str,
    label: str,
    objective_mode: str,
    config: Mapping[str, Any],
    base_dir: Path,
    execution_context: Mapping[str, Any] | None,
    include_sensitivity: bool,
    sensitivity_temp_dir: Path,
) -> DecisionAlternative:
    configured = _with_objective_mode(config, objective_mode)
    optimization = optimize_loading_parameters(configured, base_dir=base_dir)
    batch = run_profit_test(configured, base_dir=base_dir, loading_params=optimization.params)
    run_summary = build_run_summary(
        configured,
        batch,
        source=f"decision_alternative:{alternative_id}",
        execution_context=execution_context,
    )
    metrics_src = run_summary.get("summary", {})
    metrics = {
        "min_irr": float(metrics_src.get("min_irr", 0.0)),
        "min_nbv": float(metrics_src.get("min_nbv", 0.0)),
        "min_loading_surplus_ratio": float(metrics_src.get("min_loading_surplus_ratio", 0.0)),
        "max_premium_to_maturity": float(metrics_src.get("max_premium_to_maturity", 0.0)),
        "violation_count": float(metrics_src.get("violation_count", 0.0)),
    }
    params = optimization.params
    params_map = {
        "a0": float(params.a0),
        "a_age": float(params.a_age),
        "a_term": float(params.a_term),
        "a_sex": float(params.a_sex),
        "b0": float(params.b0),
        "b_age": float(params.b_age),
        "b_term": float(params.b_term),
        "b_sex": float(params.b_sex),
        "g0": float(params.g0),
        "g_term": float(params.g_term),
    }
    sensitivity_rows = (
        _build_sensitivity_rows(configured, base_dir, sensitivity_temp_dir / alternative_id)
        if include_sensitivity
        else [_scenario_summary("base", configured, base_dir)]
    )
    return DecisionAlternative(
        alternative_id=alternative_id,
        label=label,
        objective_mode=objective_mode,
        run_summary=run_summary,
        summary_df=batch.summary.sort_values("model_point"),
        cashflow_df=_aggregate_cashflow(batch),
        constraint_rows=_constraint_status_rows(run_summary),
        sensitivity_rows=sensitivity_rows,
        optimized_parameters=params_map,
        optimization_success=bool(optimization.success),
        optimization_iterations=int(optimization.iterations),
        metrics=metrics,
        batch_result=batch,
    )


def build_decision_alternatives(
    *,
    config: Mapping[str, Any],
    base_dir: Path,
    execution_context: Mapping[str, Any] | None,
    counter_objective: str,
    include_sensitivity: bool,
    language: str,
) -> tuple[DecisionAlternative, DecisionAlternative]:
    # language is kept for deterministic API parity with reporting pipeline.
    _ = language
    recommended_mode = _objective_mode(config)
    effective_counter_mode = str(counter_objective)
    if effective_counter_mode == recommended_mode:
        effective_counter_mode = (
            "penalty" if recommended_mode != "penalty" else "maximize_min_irr"
        )
    recommended = _build_alternative(
        alternative_id="recommended",
        label="推奨案",
        objective_mode=recommended_mode,
        config=config,
        base_dir=base_dir,
        execution_context=execution_context,
        include_sensitivity=include_sensitivity,
        sensitivity_temp_dir=base_dir / "out" / "sensitivity",
    )
    counter = _build_alternative(
        alternative_id="counter",
        label="対向案",
        objective_mode=effective_counter_mode,
        config=config,
        base_dir=base_dir,
        execution_context=execution_context,
        include_sensitivity=include_sensitivity,
        sensitivity_temp_dir=base_dir / "out" / "sensitivity",
    )
    return recommended, counter
