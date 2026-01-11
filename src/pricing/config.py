from __future__ import annotations

"""
Configuration helpers for pricing automation.
"""

from dataclasses import dataclass
from typing import Mapping, Sequence

from .endowment import LoadingFunctionParams


def _load_loading_params_from_mapping(
    params_cfg: Mapping[str, object] | None,
    defaults: LoadingFunctionParams,
) -> LoadingFunctionParams:
    def _get_value(key: str, default: float) -> float:
        if params_cfg is None:
            return float(default)
        raw = params_cfg.get(key, default)
        return float(raw)

    return LoadingFunctionParams(
        a0=_get_value("a0", defaults.a0),
        a_age=_get_value("a_age", defaults.a_age),
        a_term=_get_value("a_term", defaults.a_term),
        a_sex=_get_value("a_sex", defaults.a_sex),
        b0=_get_value("b0", defaults.b0),
        b_age=_get_value("b_age", defaults.b_age),
        b_term=_get_value("b_term", defaults.b_term),
        b_sex=_get_value("b_sex", defaults.b_sex),
        g0=_get_value("g0", defaults.g0),
        g_term=_get_value("g_term", defaults.g_term),
    )


def read_loading_parameters(
    config: Mapping[str, object],
) -> LoadingFunctionParams | None:
    """
    Read loading function parameters from config.

    These parameters define the alpha/beta/gamma functions used to build
    loadings, not a direct premium scaling factor.
    """
    defaults = LoadingFunctionParams(
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

    if "loading_parameters" in config:
        params_cfg = config.get("loading_parameters")
        if isinstance(params_cfg, Mapping):
            return _load_loading_params_from_mapping(params_cfg, defaults)
        return defaults

    loading_cfg = config.get("loading_function")
    if isinstance(loading_cfg, Mapping):
        params_cfg = loading_cfg.get("params")
        if isinstance(params_cfg, Mapping):
            return _load_loading_params_from_mapping(params_cfg, defaults)
        return _load_loading_params_from_mapping(loading_cfg, defaults)

    return None


@dataclass(frozen=True)
class OptimizationStage:
    """
    One optimization stage definition.

    Units
    - variables: loading function coefficient names
    """

    name: str
    variables: list[str]


@dataclass(frozen=True)
class OptimizationBounds:
    """
    Bounds definition for one coefficient.

    Units
    - min/max: coefficient value
    - step: coefficient step
    """

    min: float
    max: float
    step: float


@dataclass(frozen=True)
class OptimizationSettings:
    """
    Optimization settings for hard/soft constraints and search.

    Units
    - irr_hard/irr_target: annual rate
    - loading_surplus_hard: JPY
    - loading_surplus_hard_ratio: ratio per sum assured
    - premium_to_maturity_hard_max/target: ratio
    - nbv_hard: JPY
    - l2_lambda: weight for L2 regularization
    - max_iterations_per_stage: iteration count
    - watch_model_point_ids: model points excluded from objective/constraints
    """

    irr_hard: float
    irr_target: float
    loading_surplus_hard: float
    loading_surplus_hard_ratio: float | None
    premium_to_maturity_hard_max: float
    premium_to_maturity_target: float
    nbv_hard: float
    stages: list[OptimizationStage]
    bounds: dict[str, OptimizationBounds]
    l2_lambda: float
    max_iterations_per_stage: int
    watch_model_point_ids: list[str]


@dataclass(frozen=True)
class ExemptionSweepSettings:
    """
    Sweep settings for exemption policy.

    Units
    - start/end/step: premium_to_maturity ratio
    - irr_threshold: annual rate
    """

    start: float
    end: float
    step: float
    irr_threshold: float


@dataclass(frozen=True)
class ExemptionSettings:
    """
    Exemption policy settings for optimization.

    Units
    - enabled: policy switch
    - method: exemption method name
    """

    enabled: bool
    method: str
    sweep: ExemptionSweepSettings


def load_optimization_settings(config: Mapping[str, object]) -> OptimizationSettings:
    """
    Load optimization settings with defaults.
    """
    defaults = {
        "irr_hard": 0.07,
        "irr_target": 0.08,
        "loading_surplus_hard": 0.0,
        "loading_surplus_hard_ratio": -0.10,
        "premium_to_maturity_hard_max": 1.05,
        "premium_to_maturity_target": 1.0,
        "nbv_hard": 0.0,
        "l2_lambda": 0.1,
        "max_iterations_per_stage": 5000,
        "watch_model_point_ids": [],
    }

    constraints_cfg = config.get("constraints", {}) if isinstance(config, Mapping) else {}
    expense_cfg = config.get("expense_sufficiency", {}) if isinstance(config, Mapping) else {}
    optimization_cfg = config.get("optimization", {}) if isinstance(config, Mapping) else {}
    if not isinstance(optimization_cfg, Mapping):
        optimization_cfg = {}

    irr_hard = optimization_cfg.get(
        "irr_hard", constraints_cfg.get("irr_min", defaults["irr_hard"])
    )
    irr_target = optimization_cfg.get("irr_target", defaults["irr_target"])
    loading_surplus_hard = optimization_cfg.get(
        "loading_surplus_hard", expense_cfg.get("threshold", defaults["loading_surplus_hard"])
    )
    loading_surplus_hard_ratio = optimization_cfg.get(
        "loading_surplus_hard_ratio", defaults["loading_surplus_hard_ratio"]
    )
    premium_to_maturity_hard_max = optimization_cfg.get(
        "premium_to_maturity_hard_max", defaults["premium_to_maturity_hard_max"]
    )
    premium_to_maturity_target = optimization_cfg.get(
        "premium_to_maturity_target", defaults["premium_to_maturity_target"]
    )
    nbv_hard = optimization_cfg.get("nbv_hard", defaults["nbv_hard"])
    l2_lambda = optimization_cfg.get("l2_lambda", defaults["l2_lambda"])
    max_iterations_per_stage = optimization_cfg.get(
        "max_iterations_per_stage", defaults["max_iterations_per_stage"]
    )
    watch_ids = optimization_cfg.get(
        "watch_model_point_ids", defaults["watch_model_point_ids"]
    )
    if not isinstance(watch_ids, Sequence) or isinstance(watch_ids, (str, bytes)):
        watch_ids = []

    stage_defs = optimization_cfg.get("stages")
    if not isinstance(stage_defs, Sequence):
        stage_defs = [
            {"name": "base", "variables": ["a0", "b0", "g0"]},
            {
                "name": "age_term",
                "variables": [
                    "a0",
                    "b0",
                    "g0",
                    "a_age",
                    "a_term",
                    "b_age",
                    "b_term",
                    "g_term",
                ],
            },
            {
                "name": "sex",
                "variables": [
                    "a0",
                    "b0",
                    "g0",
                    "a_age",
                    "a_term",
                    "b_age",
                    "b_term",
                    "g_term",
                    "a_sex",
                    "b_sex",
                ],
            },
        ]

    stages: list[OptimizationStage] = []
    for stage in stage_defs:
        if not isinstance(stage, Mapping):
            continue
        name = str(stage.get("name", "stage"))
        variables = stage.get("variables", [])
        if not isinstance(variables, Sequence):
            variables = []
        stages.append(
            OptimizationStage(
                name=name,
                variables=[str(var) for var in variables],
            )
        )

    default_bounds = {
        "a0": OptimizationBounds(min=0.0, max=0.1, step=0.002),
        "a_age": OptimizationBounds(min=-0.005, max=0.005, step=0.0005),
        "a_term": OptimizationBounds(min=-0.005, max=0.005, step=0.0005),
        "a_sex": OptimizationBounds(min=-0.01, max=0.01, step=0.001),
        "b0": OptimizationBounds(min=0.0, max=0.05, step=0.001),
        "b_age": OptimizationBounds(min=-0.002, max=0.002, step=0.0002),
        "b_term": OptimizationBounds(min=-0.002, max=0.002, step=0.0002),
        "b_sex": OptimizationBounds(min=-0.01, max=0.01, step=0.001),
        "g0": OptimizationBounds(min=0.0, max=0.2, step=0.005),
        "g_term": OptimizationBounds(min=-0.02, max=0.02, step=0.002),
    }

    bounds_cfg = optimization_cfg.get("bounds", {}) if isinstance(optimization_cfg, Mapping) else {}
    bounds: dict[str, OptimizationBounds] = {}
    for key, default in default_bounds.items():
        override = bounds_cfg.get(key, {})
        if isinstance(override, Mapping):
            bounds[key] = OptimizationBounds(
                min=float(override.get("min", default.min)),
                max=float(override.get("max", default.max)),
                step=float(override.get("step", default.step)),
            )
        else:
            bounds[key] = default

    return OptimizationSettings(
        irr_hard=float(irr_hard),
        irr_target=float(irr_target),
        loading_surplus_hard=float(loading_surplus_hard),
        loading_surplus_hard_ratio=(
            None if loading_surplus_hard_ratio is None else float(loading_surplus_hard_ratio)
        ),
        premium_to_maturity_hard_max=float(premium_to_maturity_hard_max),
        premium_to_maturity_target=float(premium_to_maturity_target),
        nbv_hard=float(nbv_hard),
        stages=stages,
        bounds=bounds,
        l2_lambda=float(l2_lambda),
        max_iterations_per_stage=int(max_iterations_per_stage),
        watch_model_point_ids=[str(item) for item in watch_ids],
    )


def load_exemption_settings(config: Mapping[str, object]) -> ExemptionSettings:
    """
    Load exemption policy settings with defaults.
    """
    defaults = {
        "enabled": False,
        "method": "sweep_ptm",
        "sweep": {
            "start": 1.0,
            "end": 1.05,
            "step": 0.01,
            "irr_threshold": 0.0,
        },
    }

    optimization_cfg = config.get("optimization", {}) if isinstance(config, Mapping) else {}
    exemption_cfg = optimization_cfg.get("exemption", {}) if isinstance(optimization_cfg, Mapping) else {}
    if not isinstance(exemption_cfg, Mapping):
        exemption_cfg = {}

    enabled = bool(exemption_cfg.get("enabled", defaults["enabled"]))
    method = str(exemption_cfg.get("method", defaults["method"]))
    sweep_cfg = exemption_cfg.get("sweep", {}) if isinstance(exemption_cfg, Mapping) else {}
    if not isinstance(sweep_cfg, Mapping):
        sweep_cfg = {}

    sweep = ExemptionSweepSettings(
        start=float(sweep_cfg.get("start", defaults["sweep"]["start"])),
        end=float(sweep_cfg.get("end", defaults["sweep"]["end"])),
        step=float(sweep_cfg.get("step", defaults["sweep"]["step"])),
        irr_threshold=float(
            sweep_cfg.get("irr_threshold", defaults["sweep"]["irr_threshold"])
        ),
    )

    return ExemptionSettings(enabled=enabled, method=method, sweep=sweep)


def loading_surplus_threshold(settings: OptimizationSettings, sum_assured: int) -> float:
    """
    Compute loading surplus threshold (JPY) for a model point.
    """
    if settings.loading_surplus_hard_ratio is not None:
        return settings.loading_surplus_hard_ratio * float(sum_assured)
    return settings.loading_surplus_hard
