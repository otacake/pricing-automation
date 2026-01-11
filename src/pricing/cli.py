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
from .sweep_ptm import sweep_premium_to_maturity, sweep_premium_to_maturity_all


def _load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _format_run_output(config: dict, result) -> str:
    settings = load_optimization_settings(config)
    irr_min = settings.irr_hard
    premium_hard_max = settings.premium_to_maturity_hard_max
    nbv_hard = settings.nbv_hard
    watch_ids = set(settings.watch_model_point_ids)

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
        if row.model_point in watch_ids:
            status = "watch"
        else:
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

    if any(
        row.irr < irr_min and row.model_point not in watch_ids
        for row in result.summary.itertuples(index=False)
    ):
        lines.append("constraint_check: irr_hard failed")
    if any(
        row.loading_surplus < loading_surplus_threshold(settings, int(row.sum_assured))
        and row.model_point not in watch_ids
        for row in result.summary.itertuples(index=False)
    ):
        lines.append("constraint_check: loading_surplus_hard failed")
    if any(
        row.premium_to_maturity_ratio > premium_hard_max
        and row.model_point not in watch_ids
        for row in result.summary.itertuples(index=False)
    ):
        lines.append("constraint_check: premium_to_maturity_hard failed")
    if any(
        row.new_business_value < nbv_hard and row.model_point not in watch_ids
        for row in result.summary.itertuples(index=False)
    ):
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


def sweep_ptm_from_config(
    config_path: Path,
    model_point_label: str,
    start: float,
    end: float,
    step: float,
    irr_threshold: float,
    nbv_threshold: float,
    loading_surplus_ratio_threshold: float,
    premium_to_maturity_hard_max: float,
    out_path: Path | None,
    all_model_points: bool,
) -> int:
    """
    Sweep premium-to-maturity ratios for model points and write CSV output.
    """
    config = _load_config(config_path)
    base_dir = Path.cwd()
    output_path = out_path
    if output_path is None:
        output_path = (
            base_dir / "out/sweep_ptm_all.csv"
            if all_model_points
            else base_dir / f"out/sweep_ptm_{model_point_label}.csv"
        )

    if all_model_points:
        try:
            _, min_r_by_id = sweep_premium_to_maturity_all(
                config=config,
                base_dir=base_dir,
                start=start,
                end=end,
                step=step,
                irr_threshold=irr_threshold,
                nbv_threshold=nbv_threshold,
                loading_surplus_ratio_threshold=loading_surplus_ratio_threshold,
                premium_to_maturity_hard_max=premium_to_maturity_hard_max,
                out_path=output_path,
            )
        except ValueError as exc:
            raise SystemExit(2) from exc

        print("min_r_by_model_point")
        for model_id, min_r in min_r_by_id.items():
            if min_r is None:
                print(f"{model_id}: not found")
            else:
                print(f"{model_id}: {min_r}")
    else:
        try:
            df, min_r = sweep_premium_to_maturity(
                config=config,
                base_dir=base_dir,
                model_point_label=model_point_label,
                start=start,
                end=end,
                step=step,
                irr_threshold=irr_threshold,
                out_path=output_path,
            )
        except ValueError as exc:
            raise SystemExit(2) from exc

        print(df.to_csv(index=False))
        if min_r is None:
            print("min_r: not found")
        else:
            print(f"min_r: {min_r}")
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
    sweep_parser = subparsers.add_parser(
        "sweep-ptm", help="Sweep premium-to-maturity ratios for a model point."
    )
    sweep_parser.add_argument("config", type=str, help="Path to config YAML.")
    sweep_parser.add_argument(
        "--model-point",
        type=str,
        default="male_age30_term35",
        help="Target model point label.",
    )
    sweep_parser.add_argument("--start", type=float, required=True)
    sweep_parser.add_argument("--end", type=float, required=True)
    sweep_parser.add_argument("--step", type=float, required=True)
    sweep_parser.add_argument("--irr-threshold", type=float, default=0.04)
    sweep_parser.add_argument("--all-model-points", action="store_true")
    sweep_parser.add_argument(
        "--loading-surplus-ratio-threshold", type=float, default=-0.10
    )
    sweep_parser.add_argument("--nbv-threshold", type=float, default=0.0)
    sweep_parser.add_argument("--premium-to-maturity-hard-max", type=float, default=1.05)
    sweep_parser.add_argument("--out", type=str, default=None)

    args = parser.parse_args(argv)
    if args.command == "run":
        return run_from_config(Path(args.config))
    if args.command == "optimize":
        return optimize_from_config(Path(args.config))
    if args.command == "sweep-ptm":
        return sweep_ptm_from_config(
            Path(args.config),
            model_point_label=args.model_point,
            start=float(args.start),
            end=float(args.end),
            step=float(args.step),
            irr_threshold=float(args.irr_threshold),
            nbv_threshold=float(args.nbv_threshold),
            loading_surplus_ratio_threshold=float(args.loading_surplus_ratio_threshold),
            premium_to_maturity_hard_max=float(args.premium_to_maturity_hard_max),
            out_path=Path(args.out) if args.out else None,
            all_model_points=bool(args.all_model_points),
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
