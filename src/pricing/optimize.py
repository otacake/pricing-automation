from __future__ import annotations

"""
Optimization utilities for loading function parameters.
"""

from dataclasses import dataclass, replace
from pathlib import Path
import copy
import yaml

from .config import (
    ExemptionSettings,
    OptimizationSettings,
    OptimizationStage,
    load_exemption_settings,
    load_optimization_settings,
    loading_surplus_threshold,
    read_loading_parameters,
)
from .endowment import LoadingFunctionParams
from .profit_test import ProfitTestBatchResult, model_point_label, run_profit_test
from .sweep_ptm import sweep_premium_to_maturity_all


@dataclass(frozen=True)
class OptimizationResult:
    """
    Optimization outputs.

    Units
    - params: loading function parameters
    - success: constraint satisfaction
    - iterations: evaluation count
    - exempt_model_points: model point IDs skipped in hard constraints
    - exemption_settings: exemption policy configuration (if enabled)
    """

    params: LoadingFunctionParams
    batch_result: ProfitTestBatchResult
    success: bool
    iterations: int
    failure_details: list[str]
    exempt_model_points: list[str]
    exemption_settings: ExemptionSettings | None


@dataclass(frozen=True)
class CandidateEvaluation:
    """
    Candidate evaluation outputs.

    Units
    - objective: penalty sum (dimensionless)
    - violation: hard constraint penalty sum (dimensionless)
    """

    params: LoadingFunctionParams
    result: ProfitTestBatchResult
    feasible: bool
    objective: float
    violation: float
    irr_penalty: float
    premium_penalty: float
    l2_penalty: float
    failure_details: list[str]


def _evaluate(
    config: dict,
    base_dir: Path,
    params: LoadingFunctionParams,
    settings: OptimizationSettings,
    stage_vars: list[str],
    exempt_model_points: set[str],
) -> CandidateEvaluation:
    result = run_profit_test(config, base_dir=base_dir, loading_params=params)

    irr_penalty = 0.0
    premium_penalty = 0.0
    hard_violation = 0.0
    failure_details: list[str] = []
    for res in result.results:
        label = model_point_label(res.model_point)
        if label in exempt_model_points:
            continue
        threshold = loading_surplus_threshold(settings, res.model_point.sum_assured)
        irr_shortfall = max(settings.irr_hard - res.irr, 0.0)
        if irr_shortfall > 0:
            hard_violation += irr_shortfall * irr_shortfall
            failure_details.append(f"{label} irr_hard shortfall={irr_shortfall:.6f}")

        loading_shortfall = max(
            threshold - res.loading_surplus, 0.0
        )
        if loading_shortfall > 0:
            hard_violation += loading_shortfall * loading_shortfall
            failure_details.append(
                f"{label} loading_surplus_hard shortfall={loading_shortfall:.2f}"
            )

        premium_excess_hard = max(
            res.premium_to_maturity_ratio - settings.premium_to_maturity_hard_max, 0.0
        )
        if premium_excess_hard > 0:
            hard_violation += premium_excess_hard * premium_excess_hard
            failure_details.append(
                f"{label} premium_to_maturity_hard excess={premium_excess_hard:.6f}"
            )

        nbv_shortfall = max(settings.nbv_hard - res.new_business_value, 0.0)
        if nbv_shortfall > 0:
            hard_violation += nbv_shortfall * nbv_shortfall
            failure_details.append(
                f"{label} nbv_hard shortfall={nbv_shortfall:.2f}"
            )

        irr_gap = max(settings.irr_target - res.irr, 0.0)
        irr_penalty += irr_gap * irr_gap
        premium_gap = max(
            res.premium_to_maturity_ratio - settings.premium_to_maturity_target, 0.0
        )
        premium_penalty += premium_gap * premium_gap

    l2_penalty = 0.0
    for name in stage_vars:
        l2_penalty += getattr(params, name) ** 2
    l2_penalty *= settings.l2_lambda

    objective = irr_penalty + premium_penalty + l2_penalty
    feasible = hard_violation <= 0.0
    return CandidateEvaluation(
        params=params,
        result=result,
        feasible=feasible,
        objective=objective,
        violation=hard_violation,
        irr_penalty=irr_penalty,
        premium_penalty=premium_penalty,
        l2_penalty=l2_penalty,
        failure_details=failure_details,
    )


def _is_better_candidate(
    candidate: CandidateEvaluation,
    best: CandidateEvaluation | None,
) -> bool:
    if best is None:
        return True
    if candidate.feasible and not best.feasible:
        return True
    if candidate.feasible and best.feasible:
        return candidate.objective < best.objective - 1e-12
    if not candidate.feasible and not best.feasible:
        if candidate.violation < best.violation - 1e-12:
            return True
        if abs(candidate.violation - best.violation) <= 1e-12:
            return candidate.objective < best.objective - 1e-12
    return False


def _clamp_params(
    params: LoadingFunctionParams,
    settings: OptimizationSettings,
) -> LoadingFunctionParams:
    updated = params
    for name, bound in settings.bounds.items():
        value = getattr(updated, name)
        clamped = min(max(value, bound.min), bound.max)
        if clamped != value:
            updated = replace(updated, **{name: clamped})
    return updated


def _run_stage(
    config: dict,
    base_dir: Path,
    params: LoadingFunctionParams,
    settings: OptimizationSettings,
    stage: OptimizationStage,
    max_iterations: int,
    exempt_model_points: set[str],
) -> tuple[CandidateEvaluation, int]:
    stage_vars = list(dict.fromkeys(stage.variables))
    current_params = params
    current_eval = _evaluate(
        config, base_dir, current_params, settings, stage_vars, exempt_model_points
    )
    iterations = 1

    for _ in range(max_iterations):
        improved = False
        for name in stage_vars:
            if name not in settings.bounds:
                continue
            step = settings.bounds[name].step
            if step <= 0:
                continue
            for delta in (step, -step):
                next_value = getattr(current_params, name) + delta
                bound = settings.bounds[name]
                if next_value < bound.min or next_value > bound.max:
                    continue
                candidate_params = replace(current_params, **{name: next_value})
                candidate_eval = _evaluate(
                    config, base_dir, candidate_params, settings, stage_vars, exempt_model_points
                )
                iterations += 1
                if _is_better_candidate(candidate_eval, current_eval):
                    current_params = candidate_params
                    current_eval = candidate_eval
                    improved = True
                    break
            if improved or iterations >= max_iterations:
                break
        if not improved or iterations >= max_iterations:
            break

    return current_eval, iterations


def optimize_loading_parameters(
    config: dict,
    base_dir: Path,
) -> OptimizationResult:
    """
    Search loading function parameters that satisfy constraints.

    Units
    - base_dir: root for relative file paths
    - params: loading function coefficients (not a premium scaling factor)
    - hard constraints: irr_hard, loading_surplus_hard, premium_to_maturity_hard_max
    - hard constraints: nbv_hard, loading_surplus_hard_ratio (if used)
    - soft targets: irr_target, premium_to_maturity_target (penalized)
    - l2_lambda: L2 regularization weight for stage variables
    """
    settings = load_optimization_settings(config)
    exemption = load_exemption_settings(config)
    exempt_model_points: list[str] = []
    if exemption.enabled:
        if exemption.method != "sweep_ptm":
            raise ValueError(f"Unsupported exemption method: {exemption.method}")
        _, min_r_by_id = sweep_premium_to_maturity_all(
            config=config,
            base_dir=base_dir,
            start=exemption.sweep.start,
            end=exemption.sweep.end,
            step=exemption.sweep.step,
            irr_threshold=exemption.sweep.irr_threshold,
            nbv_threshold=-1.0e30,
            loading_surplus_ratio_threshold=-1.0e30,
            premium_to_maturity_hard_max=1.0e30,
            out_path=base_dir / "out" / "sweep_ptm_exemption.csv",
        )
        exempt_model_points = [
            model_id for model_id, min_r in min_r_by_id.items() if min_r is None
        ]
    exempt_set = set(exempt_model_points)

    base_params = read_loading_parameters(config)
    if base_params is None:
        base_params = LoadingFunctionParams(
            a0=0.03,
            a_age=0.0,
            a_term=0.0,
            a_sex=0.0,
            b0=0.007,
            b_age=0.0,
            b_term=0.0,
            b_sex=0.0,
            g0=0.03,
            g_term=0.0,
        )

    base_params = _clamp_params(base_params, settings)
    current_params = base_params
    total_iterations = 0
    best_eval: CandidateEvaluation | None = None

    for stage in settings.stages:
        stage_eval, iterations = _run_stage(
            config,
            base_dir,
            current_params,
            settings,
            stage,
            settings.max_iterations_per_stage,
            exempt_set,
        )
        total_iterations += iterations
        current_params = stage_eval.params
        if _is_better_candidate(stage_eval, best_eval):
            best_eval = stage_eval

    if best_eval is None:
        raise ValueError("Optimization search failed to evaluate.")

    return OptimizationResult(
        params=best_eval.params,
        batch_result=best_eval.result,
        success=best_eval.feasible,
        iterations=total_iterations,
        failure_details=[] if best_eval.feasible else best_eval.failure_details,
        exempt_model_points=exempt_model_points,
        exemption_settings=exemption if exemption.enabled else None,
    )


def write_optimized_config(
    config: dict,
    result: OptimizationResult,
    output_path: Path,
) -> Path:
    """
    Write an optimized config with explicit loading parameters.

    The loading parameters are function coefficients, not a premium multiplier.
    """
    updated = copy.deepcopy(config)
    updated["loading_parameters"] = {
        "a0": result.params.a0,
        "a_age": result.params.a_age,
        "a_term": result.params.a_term,
        "a_sex": result.params.a_sex,
        "b0": result.params.b0,
        "b_age": result.params.b_age,
        "b_term": result.params.b_term,
        "b_sex": result.params.b_sex,
        "g0": result.params.g0,
        "g_term": result.params.g_term,
    }

    summary = result.batch_result.summary
    updated["optimize_summary"] = {
        "min_irr": float(summary["irr"].min()),
        "min_loading_surplus": float(summary["loading_surplus"].min()),
        "max_premium_to_maturity": float(summary["premium_to_maturity_ratio"].max()),
        "iterations": result.iterations,
        "success": result.success,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(updated, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return output_path
