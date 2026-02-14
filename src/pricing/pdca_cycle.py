from __future__ import annotations

"""
Autonomous PDCA cycle runner for pricing workflows.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml

from .diagnostics import build_execution_context, build_run_summary
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


def _append_pdca_log(
    log_path: Path,
    *,
    run_id: str,
    config_path: Path,
    policy_path: Path,
    baseline_violation_count: int,
    final_violation_count: int,
    optimization_applied: bool,
    manifest_path: Path,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"## PDCA Cycle {run_id}",
        f"- config: `{config_path.as_posix()}`",
        f"- policy: `{policy_path.as_posix()}`",
        f"- baseline_violation_count: `{baseline_violation_count}`",
        f"- final_violation_count: `{final_violation_count}`",
        f"- optimization_applied: `{str(optimization_applied).lower()}`",
        f"- manifest: `{manifest_path.as_posix()}`",
        "",
    ]
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


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
    policy = load_auto_cycle_policy(policy_file)

    run_id = _utc_run_id()
    out_dir = base_dir / "out"
    reports_dir = base_dir / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    commands: list[dict[str, Any]] = []
    if not skip_tests:
        test_result = _run_tests(base_dir)
        commands.append(test_result)
        if test_result["returncode"] != 0:
            raise RuntimeError(
                "pytest failed before cycle execution. "
                f"stderr tail: {test_result['stderr_tail']}"
            )
    else:
        commands.append({"command": [sys.executable, "-m", "pytest", "-q"], "skipped": True})

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    execution_context = build_execution_context(
        config=config,
        base_dir=base_dir,
        config_path=config_path,
        command="pricing.cli run-cycle",
        argv=[str(config_path), "--policy", str(policy_file)],
    )

    baseline_result = run_profit_test(config, base_dir=base_dir)
    commands.append({"step": "baseline_run", "config_path": str(config_path)})
    baseline_summary_path = out_dir / f"run_summary_baseline_{run_id}.json"
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

    active_config = config
    active_config_path = config_path
    active_result = baseline_result
    optimized_config_path: Path | None = None
    optimization_applied = False

    if baseline_violation_count > policy.gate.max_violation_count:
        optimization_applied = True
        optimize_result = optimize_loading_parameters(config, base_dir=base_dir)
        commands.append({"step": "optimize", "config_path": str(config_path)})
        optimized_config_path = out_dir / f"{config_path.stem}.optimized_{run_id}.yaml"
        write_optimized_config(config, optimize_result, optimized_config_path)
        active_config_path = optimized_config_path
        active_config = yaml.safe_load(active_config_path.read_text(encoding="utf-8"))
        active_result = run_profit_test(active_config, base_dir=base_dir)
        commands.append({"step": "final_run", "config_path": str(active_config_path)})
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

    final_summary_path = out_dir / f"run_summary_cycle_{run_id}.json"
    write_run_summary_json(
        final_summary_path,
        active_config,
        active_result,
        source="run_cycle_final",
        execution_context=final_execution_context,
    )

    result_log_path = out_dir / f"result_cycle_{run_id}.log"
    result_excel_path = out_dir / f"result_cycle_{run_id}.xlsx"
    write_profit_test_log(result_log_path, active_config, active_result)
    write_profit_test_excel(result_excel_path, active_result)

    feasibility_deck_path: Path | None = None
    if policy.feasibility.enabled:
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

    markdown_report_path: Path | None = None
    executive_pptx_path: Path | None = None
    if policy.reporting.generate_markdown or policy.reporting.generate_executive_pptx:
        if not (policy.reporting.generate_markdown and policy.reporting.generate_executive_pptx):
            raise ValueError(
                "Current cycle implementation requires both "
                "generate_markdown and generate_executive_pptx to be enabled together."
            )
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
        )
        commands.append(
            {
                "step": "report_executive_pptx",
                "config_path": str(active_config_path),
                "report_language": policy.reporting.report_language,
                "chart_language": policy.reporting.chart_language,
            }
        )
        markdown_report_path = report_outputs.markdown_path
        executive_pptx_path = report_outputs.pptx_path

    manifest_path = out_dir / f"run_manifest_{run_id}.json"
    manifest = {
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
            "optimization_applied": optimization_applied,
        },
        "outputs": {
            "baseline_summary_path": str(baseline_summary_path),
            "final_summary_path": str(final_summary_path),
            "result_log_path": str(result_log_path),
            "result_excel_path": str(result_excel_path),
            "optimized_config_path": str(optimized_config_path) if optimized_config_path else None,
            "feasibility_deck_path": str(feasibility_deck_path) if feasibility_deck_path else None,
            "markdown_report_path": str(markdown_report_path) if markdown_report_path else None,
            "executive_pptx_path": str(executive_pptx_path) if executive_pptx_path else None,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")

    _append_pdca_log(
        reports_dir / "pdca_log.md",
        run_id=run_id,
        config_path=config_path,
        policy_path=policy_file,
        baseline_violation_count=baseline_violation_count,
        final_violation_count=final_violation_count,
        optimization_applied=optimization_applied,
        manifest_path=manifest_path,
    )

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
    )
