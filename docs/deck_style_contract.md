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
slides:
  - id: "executive_summary"
    title: "Executive Summary"
    message: "推奨価格と意思決定に必要な主要KPIを一枚で提示する。"
  - id: "decision_statement"
    title: "Decision Statement"
    message: "今回の意思決定事項と適用条件を簡潔に明示する。"
  - id: "pricing_recommendation"
    title: "Pricing Recommendation"
    message: "モデルポイント別の年払/月払保険料を提示する。"
  - id: "constraint_status"
    title: "Constraint Status"
    message: "Adequacy/Profitability/Soundnessの制約適合を示す。"
  - id: "cashflow_bridge"
    title: "Cashflow by Profit Source"
    message: "利源別キャッシュフロー推移を年度別に可視化する。"
  - id: "profit_source_decomposition"
    title: "Profit Source Decomposition"
    message: "主要年度の利源構成比較で収益ドライバーを示す。"
  - id: "sensitivity"
    title: "Sensitivity and Risks"
    message: "金利・失効・費用ショック時の耐性を示す。"
  - id: "governance"
    title: "Governance and Explainability"
    message: "数値根拠、再現コマンド、監査証跡を明示する。"
  - id: "decision_ask"
    title: "Decision Ask / Next Actions"
    message: "承認依頼と次アクション、監視トリガーを提示する。"
---

# Deck Style Contract

このファイルは経営向けデッキの唯一のスタイル定義源です。  
`report-executive-pptx --style-contract docs/deck_style_contract.md` で読み込まれます。

## Editing Rules

- YAML frontmatter のキーは削除しないでください。
- `slides` の件数は `main_slide_count` と一致させてください。
- 色コードは `#RRGGBB` 形式を推奨します。
- 日本語フォントは `Meiryo UI` を標準とし、環境差異に備えて fallback を維持してください。
- 本文は自由に編集可能ですが、機械可読な設定は frontmatter を優先します。

## Design Intent

- 1スライド1メッセージで、詳細計算は付録へ退避します。
- 装飾は控えめにし、数値の可読性を最優先します。
- 主要な定量主張はすべて `trace_map` で出典を辿れるようにします。
