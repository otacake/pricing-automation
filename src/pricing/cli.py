from __future__ import annotations

"""
CLI entrypoint for pricing automation.
"""

import argparse
from pathlib import Path

import yaml

from .config import load_optimization_settings, loading_surplus_threshold, read_loading_parameters
from .optimize import optimize_loading_parameters, write_optimized_config
from .outputs import write_optimize_log, write_profit_test_excel, write_profit_test_log
from .profit_test import run_profit_test


def _load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _format_run_output(config: dict, result) -> str:
    settings = load_optimization_settings(config)
    irr_min = settings.irr_hard
    premium_hard_max = settings.premium_to_maturity_hard_max
    nbv_hard = settings.nbv_hard

    loading_params = config.get("loading_parameters")
    if loading_params is None:
        params = read_loading_parameters(config)
        if params is not None:
            loading_params = {
                "a0": params.a0,
                "a_age": params.a_age,
                "a_term": params.a_term,
                "a_sex": params.a_sex,
                "b0": params.b0,
                "b_age": params.b_age,
                "b_term": params.b_term,
                "b_sex": params.b_sex,
                "g0": params.g0,
                "g_term": params.g_term,
            }

    lines = ["run"]
    if loading_params:
        lines.append("loading_parameters")
        for key in [
            "a0",
            "a_age",
            "a_term",
            "a_sex",
            "b0",
            "b_age",
            "b_term",
            "b_sex",
            "g0",
            "g_term",
        ]:
            if key in loading_params:
                lines.append(f"{key}: {loading_params[key]}")

    lines.append("model_point_results")
    for row in result.summary.itertuples(index=False):
        threshold = loading_surplus_threshold(settings, int(row.sum_assured))
        loading_ratio = row.loading_surplus / float(row.sum_assured)
        irr_ok = row.irr >= irr_min
        loading_ok = row.loading_surplus >= threshold
        premium_ok = row.premium_to_maturity_ratio <= premium_hard_max
        nbv_ok = row.new_business_value >= nbv_hard
        status = "pass" if irr_ok and loading_ok and premium_ok and nbv_ok else "fail"
        lines.append(
            f"{row.model_point} irr={row.irr} nbv={row.new_business_value} "
            f"loading_surplus={row.loading_surplus} premium_to_maturity={row.premium_to_maturity_ratio} "
            f"loading_surplus_threshold={threshold} loading_surplus_ratio={loading_ratio} "
            f"status={status}"
        )
        if status == "fail":
            if not irr_ok:
                lines.append(
                    f"shortfall: irr_hard {row.model_point} {irr_min - row.irr:.6f}"
                )
            if not loading_ok:
                lines.append(
                    f"shortfall: loading_surplus_hard {row.model_point} {threshold - row.loading_surplus:.2f}"
                )
            if not premium_ok:
                lines.append(
                    f"shortfall: premium_to_maturity_hard {row.model_point} {row.premium_to_maturity_ratio - premium_hard_max:.6f}"
                )
            if not nbv_ok:
                lines.append(
                    f"shortfall: nbv_hard {row.model_point} {nbv_hard - row.new_business_value:.2f}"
                )
        if row.premium_to_maturity_ratio > 1.0:
            lines.append(f"warning: premium_total_exceeds_maturity {row.model_point}")

    if any(row.irr < irr_min for row in result.summary.itertuples(index=False)):
        lines.append("constraint_check: irr_hard failed")
    if any(
        row.loading_surplus < loading_surplus_threshold(settings, int(row.sum_assured))
        for row in result.summary.itertuples(index=False)
    ):
        lines.append("constraint_check: loading_surplus_hard failed")
    if any(
        row.premium_to_maturity_ratio > premium_hard_max
        for row in result.summary.itertuples(index=False)
    ):
        lines.append("constraint_check: premium_to_maturity_hard failed")
    if any(row.new_business_value < nbv_hard for row in result.summary.itertuples(index=False)):
        lines.append("constraint_check: nbv_hard failed")

    return "\n".join(lines)


def run_from_config(config_path: Path) -> int:
    """
    Run profit test from a YAML config file and write outputs.
    """
    config = _load_config(config_path)
    base_dir = Path.cwd()
    result = run_profit_test(config, base_dir=base_dir)

    outputs_cfg = config.get("outputs", {})
    excel_path = base_dir / outputs_cfg.get("excel_path", "out/result.xlsx")
    log_path = base_dir / outputs_cfg.get("log_path", "out/result.log")

    write_profit_test_excel(excel_path, result)
    write_profit_test_log(log_path, config, result)
    print(_format_run_output(config, result))
    return 0


def optimize_from_config(config_path: Path) -> int:
    """
    Optimize loading parameters from a YAML config file.
    """
    config = _load_config(config_path)
    base_dir = Path.cwd()
    result = optimize_loading_parameters(config, base_dir=base_dir)

    outputs_cfg = config.get("outputs", {})
    log_path = base_dir / outputs_cfg.get("log_path", "out/result.log")
    write_optimize_log(log_path, config, result)

    optimized_path = outputs_cfg.get("optimized_config_path")
    if optimized_path:
        output_path = base_dir / optimized_path
    else:
        output_path = config_path.with_name(f"{config_path.stem}.optimized.yaml")
    write_optimized_config(config, result, output_path)

    print(log_path.read_text(encoding="utf-8"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pricing automation CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run profit test with a config.")
    run_parser.add_argument("config", type=str, help="Path to config YAML.")
    optimize_parser = subparsers.add_parser(
        "optimize", help="Optimize loading parameters with a config."
    )
    optimize_parser.add_argument("config", type=str, help="Path to config YAML.")

    args = parser.parse_args(argv)
    if args.command == "run":
        return run_from_config(Path(args.config))
    if args.command == "optimize":
        return optimize_from_config(Path(args.config))

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
