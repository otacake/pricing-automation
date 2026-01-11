from __future__ import annotations

"""
CLI entrypoint for pricing automation.
"""

import argparse
from pathlib import Path

import yaml

from .outputs import write_profit_test_excel, write_profit_test_log
from .profit_test import run_profit_test


def _load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


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
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pricing automation CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run profit test with a config.")
    run_parser.add_argument("config", type=str, help="Path to config YAML.")

    args = parser.parse_args(argv)
    if args.command == "run":
        return run_from_config(Path(args.config))

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
