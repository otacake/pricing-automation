from __future__ import annotations  # 型注釈の前方参照を許可するため

"""
Diagnostics helpers for structured outputs.
"""

from datetime import datetime, timezone  # タイムスタンプ生成に使うため
import hashlib  # 設定ハッシュ生成に使うため
import json  # 構造化出力のため
from typing import Any  # 型注釈に使うため

from .config import load_optimization_settings, loading_surplus_threshold  # 制約判定に使うため
from .profit_test import ProfitTestBatchResult, ProfitTestResult, model_point_label  # 結果の型を使うため


def _config_hash(config: dict) -> str:  # 設定内容のハッシュを作る
    payload = json.dumps(config, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _collect_model_point_results(result: ProfitTestBatchResult) -> dict[str, ProfitTestResult]:
    by_label: dict[str, ProfitTestResult] = {}
    for res in result.results:
        by_label[model_point_label(res.model_point)] = res
    return by_label


def _build_constraint_entry(  # 制約の診断行を作る
    constraint_type: str,
    current: float,
    threshold: float,
    comparison: str,
    strict: bool = False,
) -> dict[str, Any]:
    if comparison not in (">=", "<="):
        raise ValueError("comparison must be '>=' or '<='.")
    gap = current - threshold if comparison == ">=" else threshold - current
    ok = gap > 0.0 if strict else gap >= 0.0
    return {
        "type": constraint_type,
        "comparison": comparison,
        "current": current,
        "threshold": threshold,
        "gap": gap,
        "ok": ok,
    }


def build_run_summary(config: dict, result: ProfitTestBatchResult, source: str = "run") -> dict[str, Any]:
    settings = load_optimization_settings(config)
    watch_ids = set(settings.watch_model_point_ids)
    by_label = _collect_model_point_results(result)

    model_points: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    violating_ids: set[str] = set()

    for row in result.summary.itertuples(index=False):
        label = row.model_point
        res = by_label.get(label)
        if res is None:
            continue
        sum_assured = float(res.model_point.sum_assured)
        loading_ratio = res.loading_surplus / sum_assured
        loading_threshold = loading_surplus_threshold(settings, int(sum_assured))
        loading_positive = float(res.premiums.gross_annual_premium - res.premiums.net_annual_premium)

        constraints: list[dict[str, Any]] = [
            _build_constraint_entry("irr_hard", res.irr, settings.irr_hard, ">="),
            _build_constraint_entry("nbv_hard", res.new_business_value, settings.nbv_hard, ">="),
            _build_constraint_entry(
                "loading_surplus_hard", res.loading_surplus, loading_threshold, ">="
            ),
            _build_constraint_entry(
                "premium_to_maturity_hard_max",
                res.premium_to_maturity_ratio,
                settings.premium_to_maturity_hard_max,
                "<=",
            ),
            _build_constraint_entry("alpha_non_negative", res.loadings.alpha, 0.0, ">="),
            _build_constraint_entry("beta_non_negative", res.loadings.beta, 0.0, ">="),
            _build_constraint_entry("gamma_non_negative", res.loadings.gamma, 0.0, ">="),
            _build_constraint_entry("loading_positive", loading_positive, 0.0, ">=", strict=True),
        ]
        if settings.loading_surplus_hard_ratio is not None:
            constraints.append(
                _build_constraint_entry(
                    "loading_surplus_ratio_hard",
                    loading_ratio,
                    float(settings.loading_surplus_hard_ratio),
                    ">=",
                )
            )

        is_watch = label in watch_ids
        ok_all = all(entry["ok"] for entry in constraints)
        status = "watch" if is_watch else ("pass" if ok_all else "fail")

        for entry in constraints:
            if not entry["ok"] and not is_watch:
                violating_ids.add(label)
                violations.append(
                    {
                        "model_point": label,
                        "type": entry["type"],
                        "current_value": entry["current"],
                        "threshold": entry["threshold"],
                        "gap": entry["gap"],
                    }
                )

        model_points.append(
            {
                "model_point": label,
                "status": status,
                "watch": is_watch,
                "metrics": {
                    "irr": res.irr,
                    "nbv": res.new_business_value,
                    "loading_surplus": res.loading_surplus,
                    "loading_surplus_ratio": loading_ratio,
                    "premium_to_maturity": res.premium_to_maturity_ratio,
                    "gross_annual_premium": res.premiums.gross_annual_premium,
                    "net_annual_premium": res.premiums.net_annual_premium,
                    "sum_assured": sum_assured,
                },
                "loadings": {
                    "alpha": res.loadings.alpha,
                    "beta": res.loadings.beta,
                    "gamma": res.loadings.gamma,
                },
                "constraints": constraints,
                "profit_breakdown": res.profit_breakdown,
            }
        )

    summary_min_irr = min(result.summary["irr"]) if not result.summary.empty else float("nan")
    summary_min_nbv = min(result.summary["new_business_value"]) if not result.summary.empty else float("nan")
    summary_min_loading_ratio = (
        (result.summary["loading_surplus"] / result.summary["sum_assured"]).min()
        if not result.summary.empty
        else float("nan")
    )
    summary_max_ptm = (
        max(result.summary["premium_to_maturity_ratio"]) if not result.summary.empty else float("nan")
    )

    return {
        "meta": {
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config_hash": _config_hash(config),
        },
        "summary": {
            "model_point_count": len(model_points),
            "watch_count": len(watch_ids),
            "violation_count": len(violations),
            "violating_model_points": sorted(violating_ids),
            "min_irr": summary_min_irr,
            "min_nbv": summary_min_nbv,
            "min_loading_surplus_ratio": summary_min_loading_ratio,
            "max_premium_to_maturity": summary_max_ptm,
            "total_nbv": float(result.summary["new_business_value"].sum())
            if not result.summary.empty
            else 0.0,
        },
        "model_points": model_points,
        "violations": violations,
    }
