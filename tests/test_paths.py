from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.paths import resolve_base_dir_from_config


def test_resolve_base_dir_prefers_project_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    config_dir = repo / "configs"
    config_dir.mkdir()
    config_path = config_dir / "trial.yaml"
    config_path.write_text("run: {}\n", encoding="utf-8")

    assert resolve_base_dir_from_config(config_path) == repo


def test_resolve_base_dir_falls_back_to_config_parent(tmp_path: Path) -> None:
    config_dir = tmp_path / "a" / "b"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "trial.yaml"
    config_path.write_text("run: {}\n", encoding="utf-8")

    assert resolve_base_dir_from_config(config_path) == config_dir
