param(
    [string]$Config = "configs/trial-001.executive.optimized.yaml",
    [string]$StyleContract = "docs/deck_style_contract.md"
)

python -m pricing.cli report-executive-pptx $Config `
  --engine html_hybrid `
  --theme consulting-clean `
  --style-contract $StyleContract `
  --lang ja `
  --chart-lang en `
  --strict-quality
