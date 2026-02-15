from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ..paths import resolve_base_dir_from_config
from .alternatives import DecisionAlternative
from .procon_rules import build_procon_bundle, validate_procon_cardinality


def _as_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _safe_float(value: object, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _resolve_company_expense_path(config: Mapping[str, Any], config_path: Path) -> Path | None:
    base_dir = resolve_base_dir_from_config(config_path)
    profit_test_cfg = _as_mapping(config.get("profit_test"))
    expense_cfg = _as_mapping(profit_test_cfg.get("expense_model"))
    raw = expense_cfg.get("company_data_path")
    if not isinstance(raw, str):
        return None
    path = Path(raw)
    return path if path.is_absolute() else (base_dir / path).resolve()


def _overhead_split(config: Mapping[str, Any]) -> tuple[float, float]:
    profit_test_cfg = _as_mapping(config.get("profit_test"))
    expense_cfg = _as_mapping(profit_test_cfg.get("expense_model"))
    split_cfg = _as_mapping(expense_cfg.get("overhead_split"))
    if not split_cfg:
        split_cfg = _as_mapping(expense_cfg.get("include_overhead_as"))
    return (
        float(split_cfg.get("acquisition", 0.0)),
        float(split_cfg.get("maintenance", 0.0)),
    )


def _build_formula_catalog(
    *,
    config: Mapping[str, Any],
    config_path: Path,
    language: str,
) -> dict[str, Any]:
    company_path = _resolve_company_expense_path(config, config_path)
    split_acq, split_maint = _overhead_split(config)
    source = {
        "path": company_path.as_posix() if company_path is not None else None,
        "sha256": _sha256_file(company_path) if company_path is not None else None,
        "exists": bool(company_path and company_path.is_file()),
    }
    if language == "ja":
        rationale = [
            "会社実績CSVを単価・率に変換し、経営会議で検証可能な式へ固定化。",
            "共通費は split 係数で獲得・維持へ明示配賦し、再現実行時に同値を再計算。",
            "負値許容は行わず、予定事業費のいずれかが負の場合は即時停止。",
        ]
    else:
        rationale = [
            "Convert company actual CSV into unit costs/rates with deterministic formulas.",
            "Allocate overhead through explicit split factors for acquisition and maintenance.",
            "Stop immediately if any planned expense assumption becomes negative.",
        ]
    return {
        "planned_expense": {
            "id": "formula_expense_001",
            "formula_lines": [
                "acq_per_policy = (acq_var_total + acq_fixed_total + overhead_total * split_acq) / new_policies",
                "maint_per_policy = (maint_var_total + maint_fixed_total + overhead_total * split_maint) / inforce_avg",
                "coll_rate = coll_var_total / premium_income",
            ],
            "constraints": [
                "acq_per_policy >= 0",
                "maint_per_policy >= 0",
                "coll_rate >= 0",
            ],
            "parameters": {
                "split_acq": split_acq,
                "split_maint": split_maint,
            },
            "source": source,
            "rationale": rationale,
        }
    }


def _price_delta_table(
    recommended: DecisionAlternative,
    counter: DecisionAlternative | None,
) -> list[dict[str, Any]]:
    if counter is None:
        return []
    left = recommended.summary_df[["model_point", "gross_annual_premium"]].rename(
        columns={"gross_annual_premium": "recommended_annual_premium"}
    )
    right = counter.summary_df[["model_point", "gross_annual_premium"]].rename(
        columns={"gross_annual_premium": "counter_annual_premium"}
    )
    merged = left.merge(right, on="model_point", how="inner")
    rows: list[dict[str, Any]] = []
    for row in merged.itertuples(index=False):
        rec = float(row.recommended_annual_premium)
        ctr = float(row.counter_annual_premium)
        rows.append(
            {
                "model_point": str(row.model_point),
                "recommended_annual_premium": rec,
                "counter_annual_premium": ctr,
                "delta_recommended_minus_counter": rec - ctr,
            }
        )
    return rows


def _cashflow_totals(cashflow_df: pd.DataFrame) -> dict[str, float]:
    totals: dict[str, float] = {}
    for key in (
        "premium_income",
        "investment_income",
        "benefit_outgo",
        "expense_outgo",
        "reserve_change_outgo",
        "net_cf",
    ):
        totals[key] = float(cashflow_df[key].sum()) if key in cashflow_df.columns else 0.0
    return totals


def _build_causal_bridge(
    *,
    recommended: DecisionAlternative,
    counter: DecisionAlternative | None,
    language: str,
) -> dict[str, Any]:
    rec_totals = _cashflow_totals(recommended.cashflow_df)
    ctr_totals = _cashflow_totals(counter.cashflow_df) if counter is not None else {k: 0.0 for k in rec_totals}
    net_delta = rec_totals["net_cf"] - ctr_totals["net_cf"]
    components: list[dict[str, Any]] = []
    labels_ja = {
        "premium_income": "保険料収入",
        "investment_income": "利差益",
        "benefit_outgo": "保険金等支出",
        "expense_outgo": "事業費支出",
        "reserve_change_outgo": "責任準備金増減",
        "net_cf": "純キャッシュフロー",
    }
    for key in (
        "premium_income",
        "investment_income",
        "benefit_outgo",
        "expense_outgo",
        "reserve_change_outgo",
        "net_cf",
    ):
        delta = rec_totals[key] - ctr_totals[key]
        ratio = 0.0 if abs(net_delta) <= 1e-12 else (delta / net_delta)
        components.append(
            {
                "component": key,
                "label": labels_ja.get(key, key) if language == "ja" else key,
                "recommended_total": rec_totals[key],
                "counter_total": ctr_totals[key],
                "delta_recommended_minus_counter": delta,
                "contribution_ratio_to_net_delta": ratio,
            }
        )
    return {
        "basis": "recommended_minus_counter",
        "net_delta": net_delta,
        "components": components,
        "price_delta_by_model_point": _price_delta_table(recommended, counter),
    }


def _build_sensitivity_decomposition(
    *,
    recommended: DecisionAlternative,
    counter: DecisionAlternative | None,
) -> dict[str, Any]:
    def _rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        base_candidates = [row for row in rows if str(row.get("scenario")) == "base"]
        if not base_candidates:
            return []
        base = base_candidates[0]
        impacts: list[dict[str, Any]] = []
        for row in rows:
            scenario = str(row.get("scenario"))
            if scenario == "base":
                continue
            irr_delta = float(row.get("min_irr", 0.0)) - float(base.get("min_irr", 0.0))
            nbv_delta = float(row.get("min_nbv", 0.0)) - float(base.get("min_nbv", 0.0))
            ptm_delta = float(row.get("max_premium_to_maturity", 0.0)) - float(
                base.get("max_premium_to_maturity", 0.0)
            )
            vio_delta = float(row.get("violation_count", 0.0)) - float(base.get("violation_count", 0.0))
            risk_score = max(-irr_delta, 0.0) + max(-nbv_delta / 100000.0, 0.0) + max(ptm_delta, 0.0) + max(vio_delta, 0.0)
            impacts.append(
                {
                    "scenario": scenario,
                    "delta_min_irr": irr_delta,
                    "delta_min_nbv": nbv_delta,
                    "delta_max_ptm": ptm_delta,
                    "delta_violation_count": vio_delta,
                    "risk_score": risk_score,
                }
            )
        impacts.sort(key=lambda row: float(row["risk_score"]), reverse=True)
        return impacts

    decomposition = {
        "recommended": _rank(recommended.sensitivity_rows),
    }
    if counter is not None:
        decomposition["counter"] = _rank(counter.sensitivity_rows)
    return decomposition


def _build_causal_chain(
    *,
    language: str,
    run_summary_source_path: str,
    formula_source_path: str | None,
) -> list[dict[str, str]]:
    if language == "ja":
        return [
            {
                "claim_id": "min_irr",
                "metric": "min_irr",
                "formula_or_rule": "run_summary.summary.min_irr",
                "source": run_summary_source_path,
            },
            {
                "claim_id": "min_nbv",
                "metric": "min_nbv",
                "formula_or_rule": "run_summary.summary.min_nbv",
                "source": run_summary_source_path,
            },
            {
                "claim_id": "max_premium_to_maturity",
                "metric": "max_premium_to_maturity",
                "formula_or_rule": "run_summary.summary.max_premium_to_maturity",
                "source": run_summary_source_path,
            },
            {
                "claim_id": "violation_count",
                "metric": "violation_count",
                "formula_or_rule": "run_summary.summary.violation_count",
                "source": run_summary_source_path,
            },
            {
                "claim_id": "planned_expense_formula",
                "metric": "expense_model",
                "formula_or_rule": "formula_expense_001",
                "source": formula_source_path or "",
            },
            {
                "claim_id": "cashflow_by_source",
                "metric": "cashflow_by_source",
                "formula_or_rule": "aggregate(model_point_cashflow)",
                "source": run_summary_source_path,
            },
        ]
    return [
        {
            "claim_id": "min_irr",
            "metric": "min_irr",
            "formula_or_rule": "run_summary.summary.min_irr",
            "source": run_summary_source_path,
        }
    ]


def _causal_chain_coverage(causal_chain: list[dict[str, str]]) -> float:
    if not causal_chain:
        return 0.0
    valid = 0
    for row in causal_chain:
        if row.get("metric") and row.get("formula_or_rule") and row.get("source"):
            valid += 1
    return valid / len(causal_chain)


def _decision_compare(
    *,
    recommended: DecisionAlternative,
    counter: DecisionAlternative | None,
    language: str,
) -> dict[str, Any]:
    if counter is None:
        return {
            "enabled": False,
            "selected_alternative": "recommended",
            "integrity": {"independent_optimization": True, "reason": "comparison_disabled"},
        }

    metric_diff = {
        key: _safe_float(recommended.metrics.get(key)) - _safe_float(counter.metrics.get(key))
        for key in (
            "min_irr",
            "min_nbv",
            "min_loading_surplus_ratio",
            "max_premium_to_maturity",
            "violation_count",
        )
    }
    param_diff = any(
        abs(_safe_float(recommended.optimized_parameters.get(key)) - _safe_float(counter.optimized_parameters.get(key)))
        > 1e-12
        for key in recommended.optimized_parameters
    )
    metric_diff_exists = any(abs(value) > 1e-12 for value in metric_diff.values())
    objective_diff = recommended.objective_mode != counter.objective_mode
    integrity = bool(objective_diff and (param_diff or metric_diff_exists))

    if language == "ja":
        adoption = [
            "推奨案は制約逸脱を増やさずに最小IRR/NBVを維持する方針を採用。",
            "対向案との差分は利差益寄与とPTM上限余力のバランスで評価。",
            "許容するリスクと守るべき下限を分離して意思決定を固定化。",
        ]
    else:
        adoption = [
            "Recommended alternative selected with explicit guardrails.",
            "Decision based on IRR/NBV/PTM and cashflow decomposition gap.",
            "Risk tolerance and non-negotiable floors are separated.",
        ]
    return {
        "enabled": True,
        "selected_alternative": "recommended",
        "counter_alternative": "counter",
        "objectives": {
            "recommended": recommended.objective_mode,
            "counter": counter.objective_mode,
        },
        "metric_diff_recommended_minus_counter": metric_diff,
        "price_diff_by_model_point": _price_delta_table(recommended, counter),
        "adoption_reason": adoption,
        "integrity": {
            "independent_optimization": integrity,
            "objective_mode_different": objective_diff,
            "parameter_difference_detected": param_diff,
            "metric_difference_detected": metric_diff_exists,
        },
    }


def build_explainability_artifacts(
    *,
    config: Mapping[str, Any],
    config_path: Path,
    run_summary_source_path: str,
    recommended: DecisionAlternative,
    counter: DecisionAlternative | None,
    quant_count: int,
    qual_count: int,
    require_causal_bridge: bool,
    require_sensitivity_decomp: bool,
    language: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    formula_catalog = _build_formula_catalog(config=config, config_path=config_path, language=language)
    formula_source = _as_mapping(formula_catalog.get("planned_expense")).get("source", {})
    formula_source_path = str(_as_mapping(formula_source).get("path", ""))

    decision_compare = _decision_compare(
        recommended=recommended,
        counter=counter,
        language=language,
    )
    causal_bridge = _build_causal_bridge(
        recommended=recommended,
        counter=counter,
        language=language,
    )
    sensitivity_decomposition = _build_sensitivity_decomposition(
        recommended=recommended,
        counter=counter,
    )

    procon = {
        "recommended": build_procon_bundle(
            alternative_id="recommended",
            objective_mode=recommended.objective_mode,
            metrics=recommended.metrics,
            peer_metrics=counter.metrics if counter is not None else recommended.metrics,
            quant_count=quant_count,
            qual_count=qual_count,
            language=language,
        )
    }
    if counter is not None:
        procon["counter"] = build_procon_bundle(
            alternative_id="counter",
            objective_mode=counter.objective_mode,
            metrics=counter.metrics,
            peer_metrics=recommended.metrics,
            quant_count=quant_count,
            qual_count=qual_count,
            language=language,
        )

    causal_chain = _build_causal_chain(
        language=language,
        run_summary_source_path=run_summary_source_path,
        formula_source_path=formula_source_path,
    )
    coverage = _causal_chain_coverage(causal_chain)

    why_tree = {
        "decision": "recommended",
        "because": decision_compare.get("adoption_reason", []),
        "guardrails": [
            "violation_count == 0",
            "min_irr and min_nbv remain above hard floors",
            "max_premium_to_maturity does not exceed hard cap",
        ],
    }

    procon_ok = validate_procon_cardinality(
        procon_map=procon,
        quant_count=quant_count,
        qual_count=qual_count,
    )
    bridge_present = bool(_as_mapping(causal_bridge).get("components"))
    sensitivity_present = bool(_as_mapping(sensitivity_decomposition).get("recommended"))
    bridge_and_sensitivity_present = bool(
        (not require_causal_bridge or bridge_present)
        and (not require_sensitivity_decomp or sensitivity_present)
    )

    explainability_report = {
        "coverage_target": 1.0,
        "causal_chain_coverage": coverage,
        "causal_chain": causal_chain,
        "formula_catalog": formula_catalog,
        "causal_bridge": causal_bridge,
        "sensitivity_decomposition": sensitivity_decomposition,
        "procon": procon,
        "why_tree": why_tree,
        "checks": {
            "procon_cardinality_ok": procon_ok,
            "bridge_present": bridge_present,
            "sensitivity_present": sensitivity_present,
            "bridge_and_sensitivity_present": bridge_and_sensitivity_present,
        },
    }
    return explainability_report, decision_compare
