# exec-deck-hybrid

Generate management-ready Markdown + PPTX artifacts with an HTML/CSS preview layer and editable PPT-native objects.

## When to use

- You need `reports/*.md` and `reports/*.pptx` from existing pricing outputs.
- You want presentation styling controlled by `docs/deck_style_contract.md`.
- You require reproducible, traceable deck generation with quality gates.

## Prerequisites

1. Install Python dependencies for this repository.
2. Install Node dependencies once:

```powershell
npm --prefix tools/exec_deck_hybrid install
```

## Default command

```powershell
python -m pricing.cli report-executive-pptx configs/trial-001.executive.optimized.yaml `
  --engine html_hybrid `
  --theme consulting-clean `
  --style-contract docs/deck_style_contract.md `
  --lang ja --chart-lang en
```

## Outputs

- `reports/executive_pricing_deck.pptx`
- `reports/feasibility_report.md`
- `reports/executive_pricing_deck_preview.html`
- `out/executive_deck_spec.json`
- `out/executive_deck_quality.json`

## Quality policy

- `numeric_trace_coverage >= 1.0`
- `editable_shape_ratio >= 0.80`
- `runtime_seconds <= 180`

If `--strict-quality` is enabled (default), generation fails when a threshold is not met.
