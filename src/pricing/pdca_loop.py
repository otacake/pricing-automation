from __future__ import annotations

"""Minimal champion/challenger PDCA loop.

Each iteration optimizes loading parameters on the incumbent config.
A candidate replaces the incumbent only when the lexicographic guard accepts
it. The loop stops when a candidate is rejected, or when loop.max_iterations
is reached. status=success means the loop finished; it does not mean the
violation gate passed. Every trial is appended to the ledger.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import sys
from typing import Any, Mapping

import numpy as np
import yaml

from .acceptance import NonFiniteMetricsError, acceptance_decision, metrics_from_run_summary
from .data_quality import raise_if_data_invalid
from .diagnostics import build_run_summary
from .ledger import (
    INPUT_CONFIG_HASH_COVERS,
    append_ledger_record,
    input_config_sha256,
    record_approval_hypotheses,
    resolve_ledger_path,
    stable_config_sha256,
)
from .optimize import optimize_loading_parameters, write_optimized_config
from .paths import resolve_base_dir_from_config
from .policy import AutoCyclePolicy, load_auto_cycle_policy
from .profit_test import run_profit_test
from .validation import (
    format_validation_issues,
    has_validation_errors,
    validate_config,
)


@dataclass(frozen=True)
class PDCALoopOutputs:
    loop_id: str
    status: str
    stop_reason: str
    manifest_path: Path
    result_log_path: Path
    ledger_path: Path
    iterations_run: int
    champion_metrics: dict[str, float]
    gate_passed: bool | None
    final_violation_count: int | None
    gate_max_violation_count: int | None


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _failure_class(stage: str, exc: BaseException) -> str:
    if stage == "validate_data":
        return "data_missing"
    message = str(exc).lower()
    if "quality gate" in message:
        return "quality_gate"
    return "cycle_error"


def _validate_or_raise(config: dict, *, context: str) -> None:
    issues = validate_config(config)
    for line in format_validation_issues(issues, prefix=context):
        print(line)
    if has_validation_errors(issues):
        raise ValueError(f"{context}: configuration validation failed.")


def _write_result_log(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


EXECUTION_NOTE = (
    "status is the execution outcome; success does not mean the gate passed"
)


def record_token(value: object) -> str:
    """Render None and bool so logs match JSON null/true/false."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _violation_count(metrics: Mapping[str, object]) -> int | None:
    if not metrics:
        return None
    raw = metrics.get("violation_count")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


def evaluate_gate(
    metrics: Mapping[str, object],
    threshold: int | None,
) -> tuple[bool | None, int | None, int | None]:
    """Compare the final violation count with the policy threshold.

    Missing metrics or a missing threshold leave gate_passed as None.
    None is not a pass.
    """
    count = _violation_count(metrics)
    if count is None or threshold is None:
        return None, count, threshold
    return count <= threshold, count, threshold


def _loading_changes(config: dict) -> list[dict[str, object]]:
    params = config.get("loading_parameters")
    if not isinstance(params, dict):
        return [{"path": "loading_parameters"}]
    return [{"path": f"loading_parameters.{key}", "after": value} for key, value in params.items()]


def run_pdca_loop(
    config_path: Path,
    *,
    policy_path: Path = Path("policy/pricing_policy.yaml"),
    max_iterations: int | None = None,
) -> PDCALoopOutputs:
    config_path = config_path.expanduser().resolve()
    base_dir = resolve_base_dir_from_config(config_path)
    policy_file = policy_path if policy_path.is_absolute() else (base_dir / policy_path)
    policy_file = policy_file.resolve()
    iteration_cap = 3 if max_iterations is None else int(max_iterations)
    if iteration_cap < 1:
        raise ValueError("max_iterations must be >= 1.")
    seed = 20261005

    loop_id = _utc_run_id()
    out_dir = base_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    loop_dir = out_dir / f"pdca_loop_{loop_id}"
    loop_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = resolve_ledger_path(base_dir, "out/pdca_ledger.jsonl")
    manifest_path = out_dir / f"run_manifest_{loop_id}.json"
    result_log_path = out_dir / f"result_{loop_id}.log"

    rerun_command = [
        sys.executable,
        "-m",
        "pricing.cli",
        "pdca-loop",
        str(config_path),
        "--policy",
        str(policy_file),
        "--max-iterations",
        str(iteration_cap),
    ]
    commands: list[dict[str, Any]] = [
        {
            "step": "validate_data",
            "command": [
                sys.executable,
                "-m",
                "pricing.cli",
                "validate-data",
                str(config_path),
            ],
        },
        {
            "step": "pdca_loop",
            "command": rerun_command,
            "seed": seed,
            "config_sha256": _sha256_file(config_path),
        },
    ]
    log_lines = [
        "pdca_loop",
        f"loop_id: {loop_id}",
        f"seed: {seed}",
        f"config_sha256: {_sha256_file(config_path)}",
        f"max_iterations: {iteration_cap}",
        f"command: {' '.join(rerun_command)}",
    ]

    status = "success"
    stop_reason = "max_iterations"
    failure_class: str | None = None
    error_message: str | None = None
    caught: BaseException | None = None
    stage = "init"
    iterations_run = 0
    champion_metrics: dict[str, float] = {}
    champion_config_sha: str | None = None
    champion_input_sha: str | None = None
    gate_threshold: int | None = None

    try:
        stage = "load_policy"
        policy: AutoCyclePolicy = load_auto_cycle_policy(policy_file)
        gate_threshold = policy.gate.max_violation_count
        if max_iterations is None:
            iteration_cap = policy.loop.max_iterations
        seed = policy.loop.random_seed
        random.seed(seed)
        np.random.seed(seed)
        ledger_path = resolve_ledger_path(base_dir, policy.ledger.path)
        rerun_command = [
            sys.executable,
            "-m",
            "pricing.cli",
            "pdca-loop",
            str(config_path),
            "--policy",
            str(policy_file),
            "--max-iterations",
            str(iteration_cap),
        ]
        commands[1] = {
            "step": "pdca_loop",
            "command": rerun_command,
            "seed": seed,
            "config_sha256": _sha256_file(config_path),
        }
        log_lines[2] = f"seed: {seed}"
        log_lines[4] = f"max_iterations: {iteration_cap}"
        log_lines[5] = f"command: {' '.join(rerun_command)}"

        stage = "load_config"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        _validate_or_raise(config, context="pricing.cli pdca-loop")
        stage = "validate_data"
        raise_if_data_invalid(config, base_dir)

        stage = "incumbent_run"
        champion_config = config
        champion_result = run_profit_test(champion_config, base_dir=base_dir)
        champion_summary = build_run_summary(
            champion_config,
            champion_result,
            source="pdca_loop_incumbent",
        )
        champion_metrics_obj = metrics_from_run_summary(champion_summary)
        if not math.isfinite(champion_metrics_obj.min_irr) or not math.isfinite(
            champion_metrics_obj.premium
        ):
            raise NonFiniteMetricsError(
                "Incumbent IRR and premium must be finite before comparison."
            )
        champion_metrics = champion_metrics_obj.as_dict()
        champion_config_sha = stable_config_sha256(champion_config)
        champion_input_sha = input_config_sha256(champion_config)
        (loop_dir / "champion_initial.yaml").write_text(
            yaml.safe_dump(champion_config, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        log_lines.append(f"incumbent: {champion_metrics}")

        for iteration in range(1, iteration_cap + 1):
            iterations_run = iteration
            stage = f"optimize_{iteration}"
            optimize_result = optimize_loading_parameters(champion_config, base_dir=base_dir)
            commands.append(
                {
                    "step": "optimize",
                    "iteration": iteration,
                    "seed": seed,
                    "config_sha256": champion_config_sha,
                }
            )
            record_approval_hypotheses(
                ledger_path,
                optimize_result.approval_hypotheses,
                loop_id=loop_id,
                source="pdca_loop",
                iteration=iteration,
                seed=seed,
                config_sha256=champion_config_sha,
                input_config_hash=champion_input_sha,
            )
            for hypothesis in optimize_result.approval_hypotheses:
                log_lines.append(
                    "approval_required "
                    f"iteration={iteration} id={hypothesis.get('hypothesis_id')} applied=false"
                )

            iter_dir = loop_dir / f"iter_{iteration}"
            iter_dir.mkdir(parents=True, exist_ok=True)
            candidate_path = iter_dir / "candidate.yaml"
            write_optimized_config(champion_config, optimize_result, candidate_path)
            candidate_config = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
            stage = f"candidate_run_{iteration}"
            candidate_result = run_profit_test(candidate_config, base_dir=base_dir)
            candidate_summary = build_run_summary(
                candidate_config,
                candidate_result,
                source="pdca_loop_candidate",
            )
            candidate_metrics = metrics_from_run_summary(candidate_summary)
            decision, reason = acceptance_decision(candidate_metrics, champion_metrics_obj)
            candidate_sha = stable_config_sha256(candidate_config)
            candidate_input_sha = input_config_sha256(candidate_config)
            trial_stop_reason = reason if decision != "accepted" else None
            append_ledger_record(
                ledger_path,
                {
                    "loop_id": loop_id,
                    "source": "pdca_loop",
                    "iteration": iteration,
                    "candidate_id": f"optimize_loading_{iteration}",
                    "change_class": "auto_allowed",
                    "decision": decision,
                    "reason": reason,
                    "stop_reason": trial_stop_reason,
                    "applied": decision == "accepted",
                    "seed": seed,
                    "config_sha256": candidate_sha,
                    "input_config_sha256": candidate_input_sha,
                    "incumbent_input_config_sha256": champion_input_sha,
                    "input_config_sha256_covers": INPUT_CONFIG_HASH_COVERS,
                    "incumbent_metrics": champion_metrics_obj.as_dict(),
                    "candidate_metrics": candidate_metrics.as_dict(),
                    "changes": _loading_changes(candidate_config),
                },
            )
            log_lines.append(
                f"trial iteration={iteration} decision={decision} reason={reason} "
                f"stop_reason={record_token(trial_stop_reason)} "
                f"metrics={candidate_metrics.as_dict()} config_sha256={candidate_sha} "
                f"input_config_sha256={candidate_input_sha} "
                f"incumbent_input_config_sha256={champion_input_sha}"
            )
            if decision != "accepted":
                stop_reason = reason
                break
            champion_config = candidate_config
            champion_metrics_obj = candidate_metrics
            champion_metrics = candidate_metrics.as_dict()
            champion_config_sha = candidate_sha
            champion_input_sha = candidate_input_sha
            (loop_dir / "champion.yaml").write_text(
                candidate_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        else:
            stop_reason = "max_iterations"

        if not (loop_dir / "champion.yaml").is_file():
            (loop_dir / "champion.yaml").write_text(
                yaml.safe_dump(champion_config, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        log_lines.append(f"champion: {champion_metrics}")
    except Exception as exc:  # noqa: BLE001 - failed loops must still leave a manifest
        status = "failed"
        stop_reason = "failed"
        failure_class = _failure_class(stage, exc)
        error_message = str(exc)
        caught = exc
        log_lines.extend(
            [
                "status: failed",
                f"failed_stage: {stage}",
                f"failure_class: {failure_class}",
                f"error: {error_message}",
            ]
        )

    gate_passed, final_violation_count, gate_max_violation_count = evaluate_gate(
        champion_metrics,
        gate_threshold,
    )
    try:
        append_ledger_record(
            ledger_path,
            {
                "loop_id": loop_id,
                "source": "pdca_loop",
                "record_type": "loop_outcome",
                "decision": "stopped",
                "reason": stop_reason,
                "stop_reason": stop_reason,
                "status": status,
                "applied": False,
                "seed": seed,
                "iterations_run": iterations_run,
                "config_sha256": champion_config_sha,
                "input_config_sha256": champion_input_sha,
                "input_config_sha256_covers": INPUT_CONFIG_HASH_COVERS,
                "gate_passed": gate_passed,
                "final_violation_count": final_violation_count,
                "gate_max_violation_count": gate_max_violation_count,
            },
        )
    except Exception:
        if caught is None:
            raise

    status_line = f"status: {status}"
    if status_line not in log_lines:
        log_lines.insert(1, status_line)
    status_at = log_lines.index(status_line)
    log_lines.insert(status_at + 1, f"execution_note: {EXECUTION_NOTE}")
    log_lines.append(f"stop_reason: {stop_reason}")
    log_lines.append(f"gate_passed: {record_token(gate_passed)}")
    log_lines.append(f"final_violation_count: {record_token(final_violation_count)}")
    log_lines.append(f"gate_max_violation_count: {record_token(gate_max_violation_count)}")
    log_lines.append(f"champion_config_sha256: {champion_config_sha}")
    log_lines.append(f"input_config_sha256: {champion_input_sha}")
    log_lines.append(f"input_config_sha256_covers: {INPUT_CONFIG_HASH_COVERS}")
    _write_result_log(result_log_path, log_lines)
    manifest = {
        "run_id": loop_id,
        "kind": "pdca_loop",
        "status": status,
        "status_meaning": EXECUTION_NOTE,
        "stop_reason": stop_reason,
        "gate_passed": gate_passed,
        "final_violation_count": final_violation_count,
        "gate_max_violation_count": gate_max_violation_count,
        "failed_stage": stage if status == "failed" else None,
        "failure_class": failure_class,
        "error": error_message,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": seed,
        "iterations_run": iterations_run,
        "max_iterations": iteration_cap,
        "config": {
            "path": str(config_path),
            "sha256": _sha256_file(config_path),
        },
        "policy": {
            "path": str(policy_file),
            "sha256": _sha256_file(policy_file),
        },
        "champion_config_sha256": champion_config_sha,
        "input_config_sha256": champion_input_sha,
        "input_config_sha256_covers": INPUT_CONFIG_HASH_COVERS,
        "champion_metrics": champion_metrics,
        "commands": commands,
        "outputs": {
            "ledger_path": str(ledger_path),
            "result_log_path": str(result_log_path),
            "loop_dir": str(loop_dir),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")

    if caught is not None:
        print(f"status: {status}")
        print(f"execution_note: {EXECUTION_NOTE}")
        print(f"stop_reason: {stop_reason}")
        print(f"gate_passed: {record_token(gate_passed)}")
        print(f"final_violation_count: {record_token(final_violation_count)}")
        print(f"gate_max_violation_count: {record_token(gate_max_violation_count)}")
        print(f"wrote_manifest: {manifest_path}")
        print(f"wrote_result_log: {result_log_path}")
        raise RuntimeError(
            f"PDCA loop failed ({failure_class}) at {stage}: {error_message}. "
            f"stop_reason={stop_reason} manifest={manifest_path}"
        ) from caught

    return PDCALoopOutputs(
        loop_id=loop_id,
        status=status,
        stop_reason=stop_reason,
        manifest_path=manifest_path,
        result_log_path=result_log_path,
        ledger_path=ledger_path,
        iterations_run=iterations_run,
        champion_metrics=champion_metrics,
        gate_passed=gate_passed,
        final_violation_count=final_violation_count,
        gate_max_violation_count=gate_max_violation_count,
    )
