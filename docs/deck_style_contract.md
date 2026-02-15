---
version: "1.0"
persona: "Boardroom Conservative"
visual_signature: "Blue-Gray + Amber"
info_density: "low_with_appendix"
decoration_level: "subtle"
main_slide_count: 9
logo_policy: "none"
layout:
  slide_size_in:
    width: 13.333
    height: 7.5
  margins_in:
    left: 0.60
    right: 0.60
    top: 0.35
    bottom: 0.30
  grid:
    columns: 12
    gutter: 0.12
fonts:
  ja_primary: "Meiryo UI"
  ja_fallback: "Meiryo"
  en_primary: "Calibri"
  en_fallback: "Arial"
typography:
  title_pt: 34
  subtitle_pt: 18
  body_pt: 16
  note_pt: 11
  kpi_pt: 44
colors:
  primary: "#0B5FA5"
  secondary: "#5B6B7A"
  accent: "#F59E0B"
  positive: "#2A9D8F"
  negative: "#D1495B"
  background: "#F8FAFC"
  text: "#111827"
  grid: "#D1D5DB"
narrative:
  mode: "conclusion_first"
  comparison_layout: "dedicated_main_slide"
  text_density: "high"
  min_lines_per_main_slide: 6
  required_sections:
    - "conclusion"
    - "rationale"
    - "risk"
    - "decision_ask"
  main_compare_slide_id: "decision_statement"
slides:
  - id: "executive_summary"
    title: "Executive Summary"
    message: "結論先出しで主要KPIと経営判断を1枚で共有する。"
  - id: "decision_statement"
    title: "Decision Statement"
    message: "推奨案と対向案を同格で比較し、採否理由を明示する。"
  - id: "pricing_recommendation"
    title: "Pricing Recommendation"
    message: "モデルポイント別の最終価格Pと決定要因を説明する。"
  - id: "constraint_status"
    title: "Constraint Status"
    message: "Adequacy / Profitability / Soundness の制約充足を確認する。"
  - id: "cashflow_bridge"
    title: "Cashflow by Profit Source"
    message: "利源別キャッシュフローの構造と経営含意を示す。"
  - id: "profit_source_decomposition"
    title: "Profit Source Decomposition"
    message: "主要年度比較と利源寄与の因果分解を示す。"
  - id: "sensitivity"
    title: "Sensitivity and Risks"
    message: "支配シナリオと残余リスク、対応策を整理する。"
  - id: "governance"
    title: "Governance and Explainability"
    message: "予定事業費の式・根拠・監査証跡を明示する。"
  - id: "decision_ask"
    title: "Decision Ask / Next Actions"
    message: "決裁事項・実行条件・再実行条件を確定する。"
---

# Deck Style Contract

このファイルは経営会議向けPPTXの見た目と説明様式の唯一の定義源です。  
`python -m pricing.cli report-executive-pptx --style-contract docs/deck_style_contract.md` で読み込みます。

## 編集ルール

- YAML frontmatter の必須キーは削除しない。
- `slides` の件数は `main_slide_count` と一致させる。
- `narrative.required_sections` は固定順で維持する。
- 日本語フォントは `Meiryo UI` を優先し、`Meiryo` をフォールバックにする。
- 色は `#RRGGBB` で指定する。

## 設計意図

- 本文9枚は「結論 -> 根拠 -> リスク -> 意思決定要請」の順で統一する。
- `decision_statement` は本文内の2案比較専用スライドとして扱う。
- 主要数値は `trace_map` でソース追跡できることを前提とする。
- 詳細検証は付録（A1-A6）へ分離し、本文は意思決定に集中する。
