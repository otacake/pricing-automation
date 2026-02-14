from __future__ import annotations

"""
Configuration validation helpers.

The goal is to fail fast on high-risk misconfiguration and to surface
deprecated/ambiguous settings as explicit warnings.
"""

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ValidationIssue:
    level: str  # "warning" | "error"
    code: str
    path: str
    message: str


_KNOWN_TOP_LEVEL_KEYS = {
    "run",
    "product",
    "model_point",
    "model_points",
    "pricing",
    "loading_alpha_beta_gamma",
    "loading_parameters",
    "loading_function",
    "profit_test",
    "constraints",
    "expense_sufficiency",
    "optimization",
    "outputs",
    "optimize_summary",
}


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _add_issue(
    issues: list[ValidationIssue],
    *,
    level: str,
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append(
        ValidationIssue(
            level=level,
            code=code,
            path=path,
            message=message,
        )
    )


def _validate_top_level_keys(config: Mapping[str, object], issues: list[ValidationIssue]) -> None:
    for key in sorted(config.keys()):
        if key not in _KNOWN_TOP_LEVEL_KEYS:
            _add_issue(
                issues,
                level="warning",
                code="unknown_top_level_key",
                path=key,
                message="Unknown top-level key. Check for typos or stale settings.",
            )


def _validate_model_point_settings(config: Mapping[str, object], issues: list[ValidationIssue]) -> None:
    model_point = config.get("model_point")
    model_points = config.get("model_points")
    if model_point is not None and model_points is not None:
        _add_issue(
            issues,
            level="warning",
            code="duplicated_model_point_definition",
            path="model_point/model_points",
            message=(
                "Both model_point and model_points are set. "
                "model_points will be used and model_point can be ignored."
            ),
        )
    if model_points is not None and not isinstance(model_points, list):
        _add_issue(
            issues,
            level="error",
            code="invalid_model_points_type",
            path="model_points",
            message="model_points must be a list.",
        )
        return
    if not isinstance(model_points, list):
        return

    seen_ids: set[str] = set()
    for index, entry in enumerate(model_points):
        path = f"model_points[{index}]"
        if not isinstance(entry, Mapping):
            _add_issue(
                issues,
                level="error",
                code="invalid_model_point_entry",
                path=path,
                message="Each model point must be a mapping.",
            )
            continue
        raw_id = entry.get("id")
        if raw_id is None:
            continue
        model_id = str(raw_id)
        if model_id in seen_ids:
            _add_issue(
                issues,
                level="error",
                code="duplicate_model_point_id",
                path=f"{path}.id",
                message=f"Duplicate model point id: {model_id}",
            )
            continue
        seen_ids.add(model_id)


def _validate_interest_settings(config: Mapping[str, object], issues: list[ValidationIssue]) -> None:
    pricing = _as_mapping(config.get("pricing"))
    interest = _as_mapping(pricing.get("interest"))
    interest_type = interest.get("type")
    if interest_type is None:
        return
    if str(interest_type) != "flat":
        _add_issue(
            issues,
            level="error",
            code="unsupported_interest_type",
            path="pricing.interest.type",
            message="Only 'flat' interest type is currently supported.",
        )


def _validate_lapse_settings(config: Mapping[str, object], issues: list[ValidationIssue]) -> None:
    pricing = _as_mapping(config.get("pricing"))
    profit_test = _as_mapping(config.get("profit_test"))
    pricing_lapse_cfg = _as_mapping(pricing.get("lapse"))
    pricing_lapse = pricing_lapse_cfg.get("annual_rate")
    pt_lapse = profit_test.get("lapse_rate")
    if pricing_lapse is None or pt_lapse is None:
        return
    try:
        pricing_lapse_float = float(pricing_lapse)
        pt_lapse_float = float(pt_lapse)
    except (TypeError, ValueError):
        _add_issue(
            issues,
            level="warning",
            code="ambiguous_lapse_setting",
            path="pricing.lapse.annual_rate/profit_test.lapse_rate",
            message=(
                "Both lapse settings are present but could not be compared numerically. "
                "The engine uses profit_test.lapse_rate."
            ),
        )
        return
    if abs(pricing_lapse_float - pt_lapse_float) > 1e-12:
        _add_issue(
            issues,
            level="warning",
            code="ambiguous_lapse_setting",
            path="pricing.lapse.annual_rate/profit_test.lapse_rate",
            message=(
                "Both lapse settings are present with different values. "
                "The engine uses profit_test.lapse_rate."
            ),
        )


def _validate_expense_model_settings(config: Mapping[str, object], issues: list[ValidationIssue]) -> None:
    profit_test = _as_mapping(config.get("profit_test"))
    expense_model = _as_mapping(profit_test.get("expense_model"))
    if not expense_model:
        return

    mode = expense_model.get("mode")
    if mode is not None and str(mode) not in {"company", "loading"}:
        _add_issue(
            issues,
            level="error",
            code="unsupported_expense_mode",
            path="profit_test.expense_model.mode",
            message="expense_model.mode must be either 'company' or 'loading'.",
        )

    has_overhead_split = "overhead_split" in expense_model
    has_legacy_key = "include_overhead_as" in expense_model
    if has_overhead_split and has_legacy_key:
        _add_issue(
            issues,
            level="warning",
            code="deprecated_key_ignored",
            path="profit_test.expense_model.include_overhead_as",
            message=(
                "Both overhead_split and include_overhead_as are set. "
                "overhead_split takes precedence."
            ),
        )
    elif has_legacy_key:
        _add_issue(
            issues,
            level="warning",
            code="deprecated_key_used",
            path="profit_test.expense_model.include_overhead_as",
            message="Deprecated key in use. Migrate to overhead_split.",
        )

    overhead_cfg = _as_mapping(expense_model.get("overhead_split"))
    if not overhead_cfg:
        overhead_cfg = _as_mapping(expense_model.get("include_overhead_as"))
    if not overhead_cfg:
        return

    acq_raw = overhead_cfg.get("acquisition", 0.0)
    maint_raw = overhead_cfg.get("maintenance", 0.0)
    try:
        acq = float(acq_raw)
        maint = float(maint_raw)
    except (TypeError, ValueError):
        _add_issue(
            issues,
            level="error",
            code="invalid_overhead_split_value",
            path="profit_test.expense_model.overhead_split",
            message="acquisition/maintenance split must be numeric.",
        )
        return

    if acq < 0.0 or maint < 0.0:
        _add_issue(
            issues,
            level="error",
            code="negative_overhead_split",
            path="profit_test.expense_model.overhead_split",
            message="Overhead split values must be non-negative.",
        )
    total = acq + maint
    if abs(total - 1.0) > 1e-6:
        _add_issue(
            issues,
            level="warning",
            code="overhead_split_not_unit",
            path="profit_test.expense_model.overhead_split",
            message=(
                f"acquisition + maintenance is {total:.6f} (expected 1.0). "
                "Unallocated or over-allocated overhead may distort expense assumptions."
            ),
        )


def validate_config(config: Mapping[str, object]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    _validate_top_level_keys(config, issues)
    _validate_model_point_settings(config, issues)
    _validate_interest_settings(config, issues)
    _validate_lapse_settings(config, issues)
    _validate_expense_model_settings(config, issues)
    return issues


def has_validation_errors(issues: Iterable[ValidationIssue]) -> bool:
    return any(issue.level == "error" for issue in issues)


def format_validation_issues(
    issues: Iterable[ValidationIssue],
    *,
    prefix: str = "config_validation",
) -> list[str]:
    lines: list[str] = []
    for issue in issues:
        lines.append(
            f"{prefix}:{issue.level}: [{issue.code}] {issue.path} - {issue.message}"
        )
    return lines

