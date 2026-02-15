---
version: "2.0"
persona: "Boardroom Conservative"
visual_signature: "Blue-Gray + Amber"
info_density: "medium_with_visuals"
decoration_level: "subtle"
main_slide_count: 9
logo_policy: "none"
visual:
  icon_style: "line"
layout:
  master_variant: "consulting_clean_v2"
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
tables:
  auto_page_default: true
  auto_page_repeat_header: true
  auto_page_header_rows: 1
  auto_page_slide_start_y: 1.45
  overflow_policy: "auto_page"
charts:
  value_label_default: true
  value_label_format_code: "#,##0"
  line_value_label_format_code: "#,##0"
accessibility:
  require_unique_titles: true
  require_alt_text: true
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
  notes_mode: "auto_from_narrative"
slides:
  - id: "executive_summary"
    title: "Executive Summary"
    message: "結論先出しで、主要KPIと意思決定論点を一枚で共有する。"
  - id: "decision_statement"
    title: "Decision Statement"
    message: "推奨案と対向案を同格比較し、採否理由を明示する。"
  - id: "pricing_recommendation"
    title: "Pricing Recommendation"
    message: "モデルポイント別の最終保険料Pと算定根拠を示す。"
  - id: "constraint_status"
    title: "Constraint Status"
    message: "Adequacy / Profitability / Soundness の充足状況を確認する。"
  - id: "cashflow_bridge"
    title: "Cashflow by Profit Source"
    message: "利源別キャッシュフローの年度推移と経営含意を示す。"
  - id: "profit_source_decomposition"
    title: "Profit Source Decomposition"
    message: "主要年度差分を利源別に分解し、持続性を評価する。"
  - id: "sensitivity"
    title: "Sensitivity and Risks"
    message: "感応度順位と残余リスクを整理し、対応策を明示する。"
  - id: "governance"
    title: "Governance and Explainability"
    message: "予定事業費の式・根拠・監査証跡を明示する。"
  - id: "decision_ask"
    title: "Decision Ask / Next Actions"
    message: "決裁事項、実行計画、再実行トリガーを確定する。"
---

# Deck Style Contract (Consulting Clean v2)

このファイルは、経営会議向けデッキの見た目と情報密度を定義する唯一の設定です。  
`python -m pricing.cli report-executive-pptx --style-contract docs/deck_style_contract.md` で反映されます。

## Design Intent

- コンサルティング資料の可読性を基準に、結論先出しで構成する。
- 本文は中密度（図中心）で、監査説明は付録に展開する。
- 写真は使わず、線画アイコンと図表で統一する。
- すべての主要オブジェクトに代替テキストを付与する。

## Rules

- `slides` の件数は `main_slide_count` と一致させる。
- `narrative.required_sections` は固定順で維持する。
- `tables.auto_page_default=true` を前提に、長表のはみ出しを防止する。
- 日本語フォントは `Meiryo UI`、英語フォントは `Calibri` を使用する。
- 主要主張は `trace_map` で出典追跡できること。
