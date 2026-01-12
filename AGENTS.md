# AGENTS

## Priority Order
1. Correctness: keep tests passing and avoid silent failures.
2. Reproducibility: record commands and inputs used.
3. Clarity: explain what changed and why.

## Execution Discipline
- Run `python -m pytest -q` before any optimize/run workflow.
- Prefer the default config `configs/trial-001.yaml` unless a task specifies another.
- Avoid destructive commands and keep output files under `out/`.

## Reporting Format
- Summary of what was done.
- Metrics before/after (when applicable).
- Tests executed.
- Files changed.
- Commands run.
