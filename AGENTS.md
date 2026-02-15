# AGENTS vNext (Operating Blueprint)

## 0. Mission
Set prices that satisfy adequacy, profitability, and soundness at the same time, and deliver a reproducible and auditable decision package for management.

## 1. North Star (Success Definition)
- Pricing feasibility: `violation_count == 0` for non-watch and non-exempt model points.
- Economic quality: key constraints are met (IRR, NBV, loading surplus/ratio, PTM).
- Explainability: final pricing can be traced by formulas, coefficients, and intermediate calculations.
- Reproducibility: same inputs and same commands can reproduce the same decision.
- Decision readiness: management-grade Markdown and PPTX are generated.

## 1.5 Operating Model
- Human-readable rules: `AGENTS.md`
- Machine-readable policy: `policy/pricing_policy.yaml`
- Autonomous executor: `python -m pricing.cli run-cycle <config> --policy <policy>`

## 2. Language Boundary (Strict)
- Japanese allowed:
  - Report body text in `reports/*.md`.
  - Slide body text in `reports/*.pptx`.
- English/ASCII only:
  - CLI output, logs, tests, config keys, table/JSON/YAML keys, filenames.
  - Machine-control artifacts under `out/`.
  - Chart text (to avoid font/encoding issues).

## 3. Non-Negotiables
- Run `python -m pytest -q` before any optimize/run/report workflow.
- Use `configs/trial-001.yaml` by default unless explicitly overridden.
- Do not use destructive commands.
- Keep generated artifacts under `out/` and `reports/`.
- Use timestamped output names for manual runs (for example: `*_YYYYMMDD_HHMMSS.*`).
- Treat negative planned expense assumptions as errors and stop immediately.
- Record watch/exempt rationale in `reports/pdca_log.md`.
- Use `report-executive-pptx --engine html_hybrid` as default unless legacy compatibility is explicitly required.
- Keep `docs/deck_style_contract.md` as the single source of deck style.

## 4. Hard Gates (Stage Exit Criteria)
- Gate A: Data quality checks passed.
- Gate B: Baseline run completed and `out/run_summary*.json` generated.
- Gate C: Constraint fit achieved for non-watch/non-exempt points.
- Gate D: Sensitivity checks completed against predefined thresholds.
- Gate E: Reporting package (`.md` + `.pptx`) generated with traceable numbers.

## 5. Standard Workflow
1. Validate data quality.
2. Run baseline and capture diagnostics.
3. Optimize pricing parameters.
4. Re-run and compare before/after metrics.
5. Execute sensitivity scenarios (interest/lapse/expense shocks).
6. Generate management package (`.md` + `.pptx`).
7. Append accepted/rejected options and residual risks to `reports/pdca_log.md`.

## 5.5 Preferred Command
- Recommended one-shot execution:
  - `python -m pricing.cli run-cycle configs/trial-001.yaml --policy policy/pricing_policy.yaml`

## 6. Artifact Contract (Required Outputs Per Cycle)
- `out/run_summary_<timestamp>.json`
- `out/feasibility_deck_<timestamp>.yaml`
- `out/result_<timestamp>.log`
- `reports/feasibility_report_<timestamp>.md`
- `reports/executive_pricing_deck_<timestamp>.pptx`
- `reports/executive_pricing_deck_preview_<timestamp>.html`
- `out/executive_deck_spec_<timestamp>.json`
- `out/executive_deck_quality_<timestamp>.json`
- `reports/pdca_log.md` (append-only)
- `out/run_manifest_<timestamp>.json` (commands, hashes, versions, environment)

## 7. Reproducibility Contract
- Record:
  - config path + hash
  - input file paths + hashes
  - exact commands
  - Python version, OS, timestamp
- Fix random seeds where applicable.
- Ensure rerun consistency from the saved manifest.

## 8. Constraint Governance
- Adequacy: loading surplus and loading surplus ratio.
- Profitability: IRR and NBV.
- Soundness: PTM and expense realism.
- Watch points are monitored points, not exemptions.
- Exempt points require explicit reason, owner, scope, and review date.

## 9. Reporting Contract
### Markdown (`reports/*.md`)
- Recommendation and rationale.
- Final price table `P` (annual and monthly by model point).
- Constraint status table with worst-point gaps.
- Final alpha/beta/gamma formulas and coefficients.
- Per-model-point intermediate calculations.
- Yearly cashflow decomposition by profit source (with figure links).
- Sensitivity summary.
- Reproducibility commands.

### Executive PPTX (`reports/*.pptx`)
- Executive Summary
- Decision Statement
- Pricing Recommendation
- Constraint Status
- Cashflow by Profit Source
- Profit Source Decomposition
- Sensitivity and Risks
- Governance and Explainability
- Decision Ask / Next Actions
- One message per slide; every quantitative claim must be traceable.
- Preferred engine: `html_hybrid` (editable PPT-native objects).
- Must satisfy quality gate: `numeric_trace_coverage >= 1.0`, `editable_shape_ratio >= 0.80`, `runtime_seconds <= 180`.

## 10. Data Quality Gate (Minimum Checks)
- Required CSV columns exist.
- Types and units are valid.
- No null or duplicated model point IDs.
- `sum_assured > 0`.
- No negative planned expense assumptions.

## 11. Repository Hygiene
- Do not leave ad-hoc scratch files at repository root.
- Keep temporary artifacts in `out/` only.
- Remove obsolete files not referenced by code/tests/docs.

## 12. Agent Response Format
- Summary of what was done.
- Metrics before/after (when applicable).
- Tests executed.
- Files changed.
- Commands run.
- Open risks/assumptions.
