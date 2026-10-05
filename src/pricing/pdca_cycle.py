from __future__ import annotations

"""
Autonomous PDCA cycle runner for pricing workflows.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
from typing import Any

import yaml

from .acceptance import acceptance_decision, metrics_from_run_summary
from .data_quality import raise_if_data_invalid
from .diagnostics import build_execution_context, build_run_summary
from .ledger import (
    append_ledger_record,
    record_approval_hypotheses,
    resolve_ledger_path,
    stable_config_sha256,
)
from .optimize import optimize_loading_parameters, write_optimized_config
from .outputs import (
    write_profit_test_excel,
    write_profit_test_log,
    write_run_summary_json,
)
from .paths import resolve_base_dir_from_config
from .policy import load_auto_cycle_policy
from .profit_test import run_profit_test
from .report_executive_pptx import report_executive_pptx_from_config
from .report_feasibility import report_feasibility_from_config
from .validation import (
    format_validation_issues,
    has_validation_errors,
    validate_config,
)


@dataclass(frozen=True)
class PDCACycleOutputs:
    run_id: str
    manifest_path: Path
    baseline_summary_path: Path
    final_summary_path: Path
    result_log_path: Path
    result_excel_path: Path
    optimized_config_path: Path | None
    feasibility_deck_path: Path | None
    markdown_report_path: Path | None
    executive_pptx_path: Path | None
    executive_spec_path: Path | None = None
    executive_preview_path: Path | None = None
    executive_quality_path: Path | None = None
    executive_explainability_path: Path | None = None
    executive_compare_path: Path | None = None


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


def _run_tests(base_dir: Path) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q"]
    completed = subprocess.run(
        command,
        cwd=base_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "command": command,
        "returncode": int(completed.returncode),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _failure_class(stage: str, exc: BaseException) -> str:
    if stage == "pytest":
        return "test_failure"
    if stage == "validate_data":
        return "data_missing"
    message = str(exc).lower()
    if "quality gate" in message:
        return "quality_gate"
    if stage == "optimize":
        return "infeasible"
    return "cycle_error"


def _append_pdca_log(
    log_path: Path,
    *,
    run_id: str,
    config_path: Path,
    policy_path: Path,
    baseline_violation_count: int | None,
    final_violation_count: int | None,
    optimization_attempted: bool,
    optimization_adopted: bool,
    rejection_reason: str | None,
    status: str,
    failed_stage: str | None,
    failure_class: str | None,
    manifest_path: Path,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if status == "failed":
        outcome = (
            f"サイクルは `{failed_stage}` で失敗した（{failure_class}）。"
            "マニフェストと結果ログを残した。"
        )
    elif optimization_adopted:
        outcome = "最適化候補は辞書式目的を改善したため採用した。"
    elif optimization_attempted:
        outcome = (
            "最適化候補は違反件数の増加または辞書式目的の悪化により不採用とし、現行案を維持した。"
            f" reason={rejection_reason or 'n/a'}"
        )
    else:
        outcome = "ベースラインを現行案として維持した。"
    lines = [
        f"## PDCA Cycle {run_id}",
        f"- config: `{config_path.as_posix()}`",
        f"- policy: `{policy_path.as_posix()}`",
        f"- status: `{status}`",
        f"- failed_stage: `{failed_stage or ''}`",
        f"- failure_class: `{failure_class or ''}`",
        f"- baseline_violation_count: `{baseline_violation_count}`",
        f"- final_violation_count: `{final_violation_count}`",
        f"- optimization_attempted: `{str(optimization_attempted).lower()}`",
        f"- optimization_applied: `{str(optimization_adopted).lower()}`",
        f"- optimization_adopted: `{str(optimization_adopted).lower()}`",
        f"- rejection_reason: `{rejection_reason or ''}`",
        f"- manifest: `{manifest_path.as_posix()}`",
        f"- 結果: {outcome}",
        "",
    ]
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _validate_or_raise(config: dict, *, context: str) -> None:
    issues = validate_config(config)
    for line in format_validation_issues(issues, prefix=context):
        print(line)
    if has_validation_errors(issues):
        raise ValueError(f"{context}: configuration validation failed.")


def _append_result_log(
    path: Path,
    *,
    status: str,
    failed_stage: str | None,
    failure_class: str | None,
    error_message: str | None,
    optimization_adopted: bool,
    rejection_reason: str | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    block = "\n".join(
        [
            f"cycle_status: {status}",
            f"failed_stage: {failed_stage or ''}",
            f"failure_class: {failure_class or ''}",
            f"optimization_adopted: {str(optimization_adopted).lower()}",
            f"rejection_reason: {rejection_reason or ''}",
            f"error: {error_message or ''}",
            "",
        ]
    )
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"
        path.write_text(existing + block, encoding="utf-8")
    else:
        path.write_text(block, encoding="utf-8")


def _existing_path(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return str(path)


def run_pdca_cycle(
    config_path: Path,
    *,
    policy_path: Path = Path("policy/pricing_policy.yaml"),
    skip_tests: bool = False,
) -> PDCACycleOutputs:
    config_path = config_path.expanduser().resolve()
    base_dir = resolve_base_dir_from_config(config_path)
    policy_file = policy_path if policy_path.is_absolute() else (base_dir / policy_path)
    policy_file = policy_file.resolve()

    run_id = _utc_run_id()
    out_dir = base_dir / "out"
    reports_dir = base_dir / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = resolve_ledger_path(base_dir, "out/pdca_ledger.jsonl")
    seed = 20261005

    commands: list[dict[str, Any]] = []
    stage = "init"
    status = "success"
    failure_class: str | None = None
    error_message: str | None = None
    caught: BaseException | None = None

    baseline_violation_count: int | None = None
    final_violation_count: int | None = None
    optimization_attempted = False
    optimization_adopted = False
    rejection_reason: str | None = None
    optimized_config_path: Path | None = None
    evaluated_config_path: Path | None = None
    feasibility_deck_path: Path | None = None
    markdown_report_path: Path | None = None
    executive_pptx_path: Path | None = None
    executive_spec_path: Path | None = None
    executive_preview_path: Path | None = None
    executive_quality_path: Path | None = None
    executive_explainability_path: Path | None = None
    executive_compare_path: Path | None = None

    baseline_summary_path = out_dir / f"run_summary_baseline_{run_id}.json"
    final_summary_path = out_dir / f"run_summary_cycle_{run_id}.json"
    result_log_path = out_dir / f"result_cycle_{run_id}.log"
    result_excel_path = out_dir / f"result_cycle_{run_id}.xlsx"
    manifest_path = out_dir / f"run_manifest_{run_id}.json"

    try:
        stage = "load_policy"
        policy = load_auto_cycle_policy(policy_file)
        seed = policy.loop.random_seed
        random.seed(seed)
        ledger_path = resolve_ledger_path(base_dir, policy.ledger.path)

        stage = "pytest"
        if not skip_tests:
            test_result = _run_tests(base_dir)
            commands.append(test_result)
            if test_result["returncode"] != 0:
                raise RuntimeError(
                    "pytest failed before cycle execution. "
                    f"stderr tail: {test_result['stderr_tail']}"
                )
        else:
            commands.append(
                {"command": [sys.executable, "-m", "pytest", "-q"], "skipped": True}
            )

        stage = "load_config"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        _validate_or_raise(config, context="pricing.cli run-cycle")
        commands.append(
            {
                "step": "validate_data",
                "command": [
                    sys.executable,
                    "-m",
                    "pricing.cli",
                    "validate-data",
                    str(config_path),
                ],
            }
        )
        stage = "validate_data"
        raise_if_data_invalid(config, base_dir)

        execution_context = build_execution_context(
            config=config,
            base_dir=base_dir,
            config_path=config_path,
            command="pricing.cli run-cycle",
            argv=[str(config_path), "--policy", str(policy_file)],
        )

        stage = "baseline_run"
        baseline_result = run_profit_test(config, base_dir=base_dir)
        commands.append({"step": "baseline_run", "config_path": str(config_path)})
        write_run_summary_json(
            baseline_summary_path,
            config,
            baseline_result,
            source="run_cycle_baseline",
            execution_context=execution_context,
        )
        baseline_summary = build_run_summary(
            config,
            baseline_result,
            source="run_cycle_baseline",
            execution_context=execution_context,
        )
        baseline_violation_count = int(baseline_summary["summary"]["violation_count"])
        incumbent_metrics = metrics_from_run_summary(baseline_summary)

        active_config = config
        active_config_path = config_path
        active_result = baseline_result

        if baseline_violation_count > policy.gate.max_violation_count:
            optimization_attempted = True
            stage = "optimize"
            optimize_result = optimize_loading_parameters(config, base_dir=base_dir)
            commands.append(
                {
                    "step": "optimize",
                    "config_path": str(config_path),
                    "seed": seed,
                }
            )
            record_approval_hypotheses(
                ledger_path,
                optimize_result.approval_hypotheses,
                loop_id=run_id,
                source="run_cycle",
                iteration=1,
                seed=seed,
                config_sha256=stable_config_sha256(config),
            )
            evaluated_config_path = out_dir / f"{config_path.stem}.candidate_{run_id}.yaml"
            write_optimized_config(config, optimize_result, evaluated_config_path)
            candidate_config = yaml.safe_load(evaluated_config_path.read_text(encoding="utf-8"))
            _validate_or_raise(candidate_config, context="pricing.cli run-cycle(candidate)")
            stage = "candidate_run"
            candidate_result = run_profit_test(candidate_config, base_dir=base_dir)
            candidate_context = build_execution_context(
                config=candidate_config,
                base_dir=base_dir,
                config_path=evaluated_config_path,
                command="pricing.cli run-cycle",
                argv=[str(evaluated_config_path), "--policy", str(policy_file)],
            )
            candidate_summary = build_run_summary(
                candidate_config,
                candidate_result,
                source="run_cycle_candidate",
                execution_context=candidate_context,
            )
            candidate_metrics = metrics_from_run_summary(candidate_summary)
            decision, reason = acceptance_decision(candidate_metrics, incumbent_metrics)
            append_ledger_record(
                ledger_path,
                {
                    "loop_id": run_id,
                    "source": "run_cycle",
                    "iteration": 1,
                    "candidate_id": "optimize_loading",
                    "change_class": "auto_allowed",
                    "decision": decision,
                    "reason": reason,
                    "applied": decision == "accepted",
                    "seed": seed,
                    "config_sha256": stable_config_sha256(candidate_config),
                    "incumbent_metrics": incumbent_metrics.as_dict(),
                    "candidate_metrics": candidate_metrics.as_dict(),
                    "changes": [{"path": "loading_parameters"}],
                },
            )
            if decision == "accepted":
                optimization_adopted = True
                optimized_config_path = evaluated_config_path
                active_config = candidate_config
                active_config_path = evaluated_config_path
                active_result = candidate_result
            else:
                rejection_reason = reason
            commands.append(
                {
                    "step": "final_run",
                    "config_path": str(active_config_path),
                    "decision": decision,
                    "reason": reason,
                }
            )
        else:
            commands.append({"step": "final_run", "config_path": str(config_path)})

        final_execution_context = build_execution_context(
            config=active_config,
            base_dir=base_dir,
            config_path=active_config_path,
            command="pricing.cli run-cycle",
            argv=[str(active_config_path), "--policy", str(policy_file)],
        )
        final_summary = build_run_summary(
            active_config,
            active_result,
            source="run_cycle_final",
            execution_context=final_execution_context,
        )
        final_violation_count = int(final_summary["summary"]["violation_count"])
        stage = "final_run"
        write_run_summary_json(
            final_summary_path,
            active_config,
            active_result,
            source="run_cycle_final",
            execution_context=final_execution_context,
        )
        write_profit_test_log(result_log_path, active_config, active_result)
        write_profit_test_excel(result_excel_path, active_result)

        if policy.feasibility.enabled:
            stage = "report_feasibility"
            feasibility_deck_path = out_dir / f"feasibility_deck_cycle_{run_id}.yaml"
            commands.append(
                {
                    "step": "report_feasibility",
                    "config_path": str(active_config_path),
                    "r_start": policy.feasibility.r_start,
                    "r_end": policy.feasibility.r_end,
                    "r_step": policy.feasibility.r_step,
                    "irr_threshold": policy.feasibility.irr_threshold,
                }
            )
            report_feasibility_from_config(
                active_config_path,
                r_start=policy.feasibility.r_start,
                r_end=policy.feasibility.r_end,
                r_step=policy.feasibility.r_step,
                irr_threshold=policy.feasibility.irr_threshold,
                out_path=feasibility_deck_path,
            )

        if policy.reporting.generate_markdown or policy.reporting.generate_executive_pptx:
            if not (policy.reporting.generate_markdown and policy.reporting.generate_executive_pptx):
                raise ValueError(
                    "Current cycle implementation requires both "
                    "generate_markdown and generate_executive_pptx to be enabled together."
                )
            stage = "report_executive_pptx"
            report_outputs = report_executive_pptx_from_config(
                active_config_path,
                out_path=reports_dir / f"executive_pricing_deck_{run_id}.pptx",
                markdown_path=reports_dir / f"feasibility_report_{run_id}.md",
                run_summary_path=out_dir / f"run_summary_executive_{run_id}.json",
                deck_out_path=out_dir / f"feasibility_deck_executive_{run_id}.yaml",
                chart_dir=out_dir / "charts" / "executive" / run_id,
                r_start=policy.feasibility.r_start,
                r_end=policy.feasibility.r_end,
                r_step=policy.feasibility.r_step,
                irr_threshold=policy.feasibility.irr_threshold,
                language=policy.reporting.report_language,
                chart_language=policy.reporting.chart_language,
                theme=policy.reporting.pptx_theme,
                style_contract_path=Path(policy.reporting.style_contract_path),
                spec_out_path=out_dir / f"executive_deck_spec_{run_id}.json",
                preview_html_path=reports_dir / f"executive_pricing_deck_preview_{run_id}.html",
                quality_out_path=out_dir / f"executive_deck_quality_{run_id}.json",
                strict_quality=policy.reporting.strict_quality_gate,
                decision_compare="on" if policy.reporting.decision_compare.enabled else "off",
                counter_objective=policy.reporting.decision_compare.counter_objective,
                explainability_strict=policy.reporting.explainability.strict_gate,
                explain_out_path=out_dir / f"explainability_report_{run_id}.json",
                compare_out_path=out_dir / f"decision_compare_{run_id}.json",
                procon_quant_count=policy.reporting.explainability.procon_quant_count,
                procon_qual_count=policy.reporting.explainability.procon_qual_count,
                require_causal_bridge=policy.reporting.explainability.require_causal_bridge,
                require_sensitivity_decomp=policy.reporting.explainability.require_sensitivity_decomp,
            )
            commands.append(
                {
                    "step": "report_executive_pptx",
                    "config_path": str(active_config_path),
                    "report_language": policy.reporting.report_language,
                    "chart_language": policy.reporting.chart_language,
                    "pptx_backend": "pptxgenjs",
                    "pptx_theme": policy.reporting.pptx_theme,
                    "style_contract_path": policy.reporting.style_contract_path,
                    "strict_quality_gate": policy.reporting.strict_quality_gate,
                    "decision_compare_enabled": policy.reporting.decision_compare.enabled,
                    "counter_objective": policy.reporting.decision_compare.counter_objective,
                    "explainability_strict_gate": policy.reporting.explainability.strict_gate,
                }
            )
            markdown_report_path = report_outputs.markdown_path
            executive_pptx_path = report_outputs.pptx_path
            executive_spec_path = report_outputs.spec_path
            executive_preview_path = report_outputs.preview_html_path
            executive_quality_path = report_outputs.quality_path
            executive_explainability_path = report_outputs.explainability_path
            executive_compare_path = report_outputs.decision_compare_path
    except Exception as exc:  # noqa: BLE001 - record every failed cycle before re-raising
        status = "failed"
        failure_class = _failure_class(stage, exc)
        error_message = str(exc)
        caught = exc

    manifest = {
        "run_id": run_id,
        "status": status,
        "failed_stage": stage if status == "failed" else None,
        "failure_class": failure_class,
        "error": error_message,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": seed,
        "config": {
            "path": str(config_path),
            "sha256": _sha256_file(config_path),
        },
        "policy": {
            "path": str(policy_file),
            "sha256": _sha256_file(policy_file),
        },
        "commands": commands,
        "metrics": {
            "baseline_violation_count": baseline_violation_count,
            "final_violation_count": final_violation_count,
            "optimization_attempted": optimization_attempted,
            "optimization_applied": optimization_adopted,
            "optimization_adopted": optimization_adopted,
            "rejection_reason": rejection_reason,
        },
        "outputs": {
            "baseline_summary_path": _existing_path(baseline_summary_path),
            "final_summary_path": _existing_path(final_summary_path),
            "result_log_path": str(result_log_path),
            "result_excel_path": _existing_path(result_excel_path),
            "optimized_config_path": str(optimized_config_path) if optimized_config_path else None,
            "evaluated_config_path": str(evaluated_config_path) if evaluated_config_path else None,
            "ledger_path": str(ledger_path),
            "feasibility_deck_path": str(feasibility_deck_path) if feasibility_deck_path else None,
            "markdown_report_path": str(markdown_report_path) if markdown_report_path else None,
            "executive_pptx_path": str(executive_pptx_path) if executive_pptx_path else None,
            "executive_spec_path": str(executive_spec_path) if executive_spec_path else None,
            "executive_preview_path": str(executive_preview_path) if executive_preview_path else None,
            "executive_quality_path": str(executive_quality_path) if executive_quality_path else None,
            "executive_explainability_path": str(executive_explainability_path)
            if executive_explainability_path
            else None,
            "executive_compare_path": str(executive_compare_path) if executive_compare_path else None,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
    _append_result_log(
        result_log_path,
        status=status,
        failed_stage=stage if status == "failed" else None,
        failure_class=failure_class,
        error_message=error_message,
        optimization_adopted=optimization_adopted,
        rejection_reason=rejection_reason,
    )
    _append_pdca_log(
        reports_dir / "pdca_log.md",
        run_id=run_id,
        config_path=config_path,
        policy_path=policy_file,
        baseline_violation_count=baseline_violation_count,
        final_violation_count=final_violation_count,
        optimization_attempted=optimization_attempted,
        optimization_adopted=optimization_adopted,
        rejection_reason=rejection_reason,
        status=status,
        failed_stage=stage if status == "failed" else None,
        failure_class=failure_class,
        manifest_path=manifest_path,
    )

    if caught is not None:
        print(f"wrote_manifest: {manifest_path}")
        print(f"wrote_result_log: {result_log_path}")
        raise RuntimeError(
            f"PDCA cycle failed ({failure_class}) at {stage}: {error_message}. "
            f"manifest={manifest_path}"
        ) from caught

    return PDCACycleOutputs(
        run_id=run_id,
        manifest_path=manifest_path,
        baseline_summary_path=baseline_summary_path,
        final_summary_path=final_summary_path,
        result_log_path=result_log_path,
        result_excel_path=result_excel_path,
        optimized_config_path=optimized_config_path,
        feasibility_deck_path=feasibility_deck_path,
        markdown_report_path=markdown_report_path,
        executive_pptx_path=executive_pptx_path,
        executive_spec_path=executive_spec_path,
        executive_preview_path=executive_preview_path,
        executive_quality_path=executive_quality_path,
        executive_explainability_path=executive_explainability_path,
        executive_compare_path=executive_compare_path,
    )
