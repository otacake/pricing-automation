# AGENTS

# shell
- Use PowerShell
- Use encoding utf-8


## Mission
Set prices that satisfy adequacy, profitability, and soundness at the same time,
and make every recommendation reproducible and explainable.
Deliverables must include both practitioner-facing Markdown and executive-facing PPTX.

## Priority Order
1. Correctness: keep tests passing and prevent silent failures.
2. Reproducibility: log inputs, commands, environment, and outputs.
3. Explainability: keep formulas, coefficients, and per-model-point calculations auditable.
4. Delivery: produce decision-ready `.md` and `.pptx` artifacts.

## Non-Negotiable Rules
- Run `python -m pytest -q` before any `optimize` / `run` / `report-feasibility` workflow.
- Use `configs/trial-001.yaml` unless another config is explicitly requested.
- Avoid destructive commands (for example, `git reset --hard`).
- Keep generated artifacts under `out/` and `reports/`.
- Whenever a PDCA cycle is run, update `reports/feasibility_report.md`.
- In `reports/feasibility_report.md`, include final alpha/beta/gamma formulas, coefficients,
  and per-model-point calculations with intermediate steps.
- In the company expense model, negative planned expense assumptions are errors.
  Stop immediately; do not auto-correct and continue.

## Autonomous Workflow (PDCA)
1. Plan
- Define objective function, constraints, and watch model points.
- Define pass criteria (for example: `violation_count == 0`, `min_irr >= threshold`, `max_ptm <= hard_max`).

2. Do
- Run baseline with `run` and `report-feasibility`.
- Execute `optimize` / `propose-change` / `sweep-ptm` as needed.
- Record config path, input files, command lines, and output paths for each run.

3. Check
- Validate constraints and key metrics in `out/run_summary.json`.
- Review adequacy (loading surplus), profitability (IRR/NBV), and soundness (PTM and expense assumptions)
  by model point.
- For deviations, provide factor decomposition and reproducible rerun steps.

4. Act
- Log accepted/rejected options and rationale in `reports/pdca_log.md`.
- Write final formulas, coefficients, and evidence into `reports/feasibility_report.md`.

## Reproducibility Artifacts (Required)
For each execution, save:
- Config path and hash
- Input file paths and hashes (mortality, spot, company expense)
- Command line, timestamp, Python version, and platform
- Primary outputs:
  - `out/run_summary.json`
  - `out/result_*.log`
  - `out/result_*.xlsx`
  - `out/feasibility_deck.yaml`
  - `reports/feasibility_report.md`
  - `reports/pdca_log.md`

## Management Deliverables
1. Markdown report: `reports/feasibility_report.md`
- Recommended price and decision rationale
- Final alpha/beta/gamma formulas and coefficients
- Per-model-point calculations including intermediate values
- Constraint status (adequacy / profitability / soundness)
- Commands and rerun procedure

2. Executive deck: `reports/executive_pricing_deck.pptx`
- McKinsey-style concise storyline.
- Minimum sections:
  - Executive Summary
  - Pricing Recommendation
  - Constraint Status (Adequacy / Profitability / Soundness)
  - Cashflow by Profit Source
  - Sensitivity and Risks
  - Decision Ask / Next Actions
- Rule: one message per slide, and every quantitative claim must be traceable to reproducible evidence.

## Response Format (Agent)
- Summary of what was done
- Metrics before/after (when applicable)
- Tests executed
- Files changed
- Commands run
- Open risks / assumptions
