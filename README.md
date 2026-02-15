# Pricing Automation (Beginner Guide)

このリポジトリは、**養老保険のプライシングを再現可能に実行するための学習用プロジェクト**です。  
YAML設定 + CSVデータを入力にして、以下を行います。

- 保険料計算
- 年度別キャッシュフロー計算
- IRR / NBV / 制約評価
- loading係数の最適化
- 実現可能性レポート生成
- 経営層向けPPTX生成（HTML/CSSプレビュー付き）

---

## 1. まず何ができるか

- `python -m pricing.cli run ...`
  - 収益性検証（Excel / log / run_summary.json）
- `python -m pricing.cli optimize ...`
  - 制約を満たすように loading 係数を探索
- `python -m pricing.cli sweep-ptm ...`
  - premium-to-maturity の掃引分析
- `python -m pricing.cli report-feasibility ...`
  - 実現可能性デッキ（YAML）生成
- `python -m pricing.cli report-executive-pptx ...`
  - `reports/feasibility_report.md` と `reports/executive_pricing_deck.pptx` を生成
  - PptxGenJSバックエンドで `preview.html` と `deck_spec.json` も生成
  - 本文9枚は `結論 -> 根拠 -> リスク -> 意思決定要請` の順で固定
  - `Decision Statement` は本文内の2案比較（推奨案/対向案）専用スライド
  - 既定は日本語出力（`--lang en` で英語に切替可）
  - グラフ文字は既定で英語（`--chart-lang en`）
- `python -m pricing.cli run-cycle ...`
  - ポリシーに基づくPDCA一括実行（test→run→optimize→report）

---

## 2. 5分で動かす

前提:
- Python 3.11+
- Node.js 20+（PptxGenJSバックエンド利用のため必須）
- PowerShell

### 2.1 セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
npm --prefix tools/exec_deck_hybrid install
```

### 2.2 テスト

```powershell
python -m pytest -q
```

### 2.3 ベースライン実行

```powershell
python -m pricing.cli run configs\trial-001.yaml
```

生成物（例）:
- `out/result_trial-001.xlsx`
- `out/result_trial-001.log`
- `out/run_summary.json`

### 2.4 経営向け成果物まで一気に

```powershell
python -m pricing.cli report-executive-pptx configs\trial-001.executive.optimized.yaml `
  --theme consulting-clean-v2 `
  --style-contract docs/deck_style_contract.md `
  --decision-compare on `
  --counter-objective maximize_min_irr `
  --explainability-strict `
  --lang ja --chart-lang en
```

生成物（既定）:
- `reports/feasibility_report.md`
- `reports/executive_pricing_deck.pptx`
- `reports/executive_pricing_deck_preview.html`
- `out/run_summary_executive.json`
- `out/feasibility_deck_executive.yaml`
- `out/executive_deck_spec.json`
- `out/executive_deck_quality.json`
- `out/explainability_report.json`
- `out/decision_compare.json`
- `out/charts/executive/*.png`

`out/executive_deck_spec.json` には以下が追加されます:
- `management_narrative`（本文9枚の説明ブロック）
- `main_slide_checks`（行数・必須セクション・2案比較明示の判定）

`out/executive_deck_quality.json` では、従来の品質判定に加えて以下を確認します:
- `main_compare_present`（本文で2案比較が明示されているか）
- `main_narrative_coverage`（全本文で必須セクションが揃っているか）
- `main_narrative_density_ok`（最低行数を満たしているか）
- `decision_style_ok`（結論先出し構造が維持されているか）
- `alt_text_coverage`（チャート/画像の代替テキストが付与されているか）
- `speaker_notes_coverage`（本文スライドに発表ノートが付与されているか）
- `table_overflow_ok`（表がはみ出さずにレンダリングできるか）
- `unique_titles_ok`（スライドタイトルが一意か）

またはPDCAを一括実行:

```powershell
python -m pricing.cli run-cycle configs\trial-001.yaml --policy policy/pricing_policy.yaml
```

### 2.5 直近の実行サンプル（2026-02-15）

実行コマンド:

```powershell
python -m pricing.cli run-cycle configs\trial-001.yaml --policy policy/pricing_policy.yaml --skip-tests
```

実行ID:
- `20260215_131457`

主要結果:
- `baseline_violation_count: 6 -> final_violation_count: 0`
- `optimization_applied: true`
- `out/executive_deck_quality_20260215_131457.json: passed = true`
- `reports/executive_pricing_deck_20260215_131457.pptx` を生成

主要出力:
- `out/run_manifest_20260215_131457.json`
- `out/run_summary_cycle_20260215_131457.json`
- `out/executive_deck_spec_20260215_131457.json`
- `out/executive_deck_quality_20260215_131457.json`
- `out/explainability_report_20260215_131457.json`
- `out/decision_compare_20260215_131457.json`
- `reports/feasibility_report_20260215_131457.md`
- `reports/executive_pricing_deck_20260215_131457.pptx`
- `reports/executive_pricing_deck_preview_20260215_131457.html`

見た目を変える場合:

- `docs/deck_style_contract.md` を編集（色・余白・フォント・9枚構成）
- `narrative` ブロックで本文様式を固定（結論先出し、2案比較専用、最低6行）
- 同じコマンドを再実行すればPPTとHTMLプレビューに反映

`narrative` の必須キー:
- `mode: conclusion_first`
- `comparison_layout: dedicated_main_slide`
- `text_density: high`
- `min_lines_per_main_slide: 6`
- `required_sections: [conclusion, rationale, risk, decision_ask]`
- `main_compare_slide_id: decision_statement`

意思決定比較・監査説明を有効化する場合（既定で有効）:
- `--decision-compare on`
- `--counter-objective maximize_min_irr`
- `--explainability-strict`
- 生成: `out/explainability_report*.json`, `out/decision_compare*.json`

### Design Quality Checklist（consulting-clean-v2）

- 9枚本文 + 付録A1-A6を維持している
- `Decision Statement` が推奨案/対向案の比較専用になっている
- 本文で `conclusion -> rationale -> risk -> decision_ask` が揃っている
- 主要チャート/画像に `altText` が付いている
- 本文スライドに `speaker notes` が付いている
- 表がはみ出さず（`autoPage`）に表示される
- `out/executive_deck_quality*.json` の新指標が `true`

### テンプレート変数（style contract）

- `layout.master_variant`: masterの種類（`consulting_clean_v2`）
- `visual.icon_style`: アイコン方針（線画など）
- `tables.auto_page_default`: 表の自動ページ分割有無
- `charts.value_label_default`: グラフ値ラベル表示
- `accessibility.require_alt_text`: altText必須化
- `narrative.notes_mode`: ノート生成方針（`auto_from_narrative`）

### デザイン変更手順（style contract中心）

1. `docs/deck_style_contract.md` の frontmatter を編集（色・余白・フォント・narrative）。
2. `python -m pricing.cli report-executive-pptx ... --theme consulting-clean-v2 --style-contract docs/deck_style_contract.md` を再実行。
3. `reports/executive_pricing_deck_preview.html` で見た目を確認。
4. `out/executive_deck_quality.json` の `passed: true` を確認。

---

## 3. ディレクトリ構成

|パス|役割|
|---|---|
|`src/pricing/cli.py`|CLIの入口|
|`src/pricing/profit_test.py`|年度キャッシュフロー・IRR/NBV計算の中核|
|`src/pricing/endowment.py`|保険料率の数式（A, a, net_rate, gross_rate）|
|`src/pricing/optimize.py`|loading係数の探索（制約付き）|
|`src/pricing/diagnostics.py`|`run_summary.json` 構造化出力|
|`src/pricing/report_feasibility.py`|実現可能性YAMLデッキ生成|
|`src/pricing/report_executive_pptx.py`|Markdown + PPTXの生成|
|`src/pricing/reporting/*`|style/spec/qualityの補助モジュール|
|`docs/deck_style_contract.md`|デッキ見た目の唯一定義源（編集用）|
|`tools/exec_deck_hybrid/*`|HTMLプレビュー + PPTXレンダラ（Node）|
|`skills/exec-deck-hybrid/*`|実行手順をまとめたSkill|
|`docs/script_relationships.md`|スクリプト間の関係メモ（入口->計算->出力）|
|`configs/*.yaml`|実験設定|
|`data/*.csv`|入力データ|
|`out/`|実行出力（中間・分析用）|
|`reports/`|最終レポート類|
|`tests/`|回帰テスト|

---

## 4. 初学者向けの使い方（推奨順）

### Step 1: 現状を把握する

```powershell
python -m pricing.cli run configs\trial-001.yaml
```

- まず `out/run_summary.json` を見る
- `summary.violation_count` が 0 か確認
- どの制約が厳しいかは `violations` を見る

### Step 2: 係数を最適化する

```powershell
python -m pricing.cli optimize configs\trial-001.yaml
```

- `configs/trial-001.optimized.yaml` が生成される
- `out/result_trial-001.log` で最小IRRや失敗理由を確認

### Step 3: 最適化後を再実行して確認する

```powershell
python -m pricing.cli run configs\trial-001.optimized.yaml
```

### Step 4: 感度・境界を見る

```powershell
python -m pricing.cli sweep-ptm configs\trial-001.yaml --all-model-points --start 1.00 --end 1.08 --step 0.01
```

### Step 5: 最終レポートを作る

```powershell
python -m pricing.cli report-executive-pptx configs\trial-001.executive.optimized.yaml `
  --style-contract docs/deck_style_contract.md `
  --lang ja --chart-lang en
```

---

## 5. CLIコマンド一覧

### `run`

```powershell
python -m pricing.cli run <config.yaml>
```

- 収益性検証の標準実行

### `optimize`

```powershell
python -m pricing.cli optimize <config.yaml>
```

- loading係数（a0, a_age, ...）を探索

### `propose-change`

```powershell
python -m pricing.cli propose-change <config.yaml> --set optimization.irr_hard=0.02 --reason "tighten floor"
```

- 設定を保存せずに「変更の影響だけ」評価

### `sweep-ptm`

```powershell
python -m pricing.cli sweep-ptm <config.yaml> --model-point male_age30_term35 --start 1.00 --end 1.08 --step 0.01
python -m pricing.cli sweep-ptm <config.yaml> --all-model-points --start 1.00 --end 1.08 --step 0.01
```

### `report-feasibility`

```powershell
python -m pricing.cli report-feasibility <config.yaml> --r-start 1.00 --r-end 1.08 --r-step 0.005 --irr-threshold 0.02
```

### `report-executive-pptx`

```powershell
python -m pricing.cli report-executive-pptx <config.yaml> `
  --out reports/executive_pricing_deck.pptx `
  --md-out reports/feasibility_report.md `
  --run-summary-out out/run_summary_executive.json `
  --deck-out out/feasibility_deck_executive.yaml `
  --chart-dir out/charts/executive `
  --theme consulting-clean-v2 `
  --style-contract docs/deck_style_contract.md `
  --spec-out out/executive_deck_spec.json `
  --preview-html-out reports/executive_pricing_deck_preview.html `
  --quality-out out/executive_deck_quality.json `
  --strict-quality `
  --decision-compare on `
  --counter-objective maximize_min_irr `
  --explainability-strict `
  --explain-out out/explainability_report.json `
  --compare-out out/decision_compare.json `
  --lang ja `
  --chart-lang en
```

### `run-cycle`

```powershell
python -m pricing.cli run-cycle <config.yaml> --policy policy/pricing_policy.yaml
```

### Breaking Change: PPTX Backend / Theme

- 旧: `report-executive-pptx --engine legacy`
- 新: `--engine` オプションは廃止。PPTX生成は常に PptxGenJS バックエンド
- 推奨テーマ: `consulting-clean-v2`（互換エイリアス `consulting-clean` は利用可能）
- policy移行:
  - `reporting.pptx_engine` は削除
  - 既存policyで `pptx_engine: legacy` がある場合はエラー停止
  - `pptx_engine: html_hybrid` は互換入力として読み飛ばされる（削除推奨）

---

## 6. 設定ファイルの読み方（`configs/trial-001.yaml`）

重要キー:

- `model_points`: 対象契約群
- `pricing.interest.flat_rate`: 予定利率
- `pricing.mortality_path`: 予定死亡率CSV
- `profit_test.discount_curve_path`: 割引用スポットカーブCSV
- `profit_test.mortality_actual_path`: 実績死亡率CSV
- `profit_test.expense_model.company_data_path`: 会社費用CSV
- `loading_alpha_beta_gamma` または `loading_parameters`: loading設定
- `optimization.*`: 制約と最適化挙動

補足:
- `loading_parameters` があればそちらが優先
- 相対パスは **設定ファイル位置から解決**（`cwd`依存ではない）

---

## 7. 入力CSV仕様

|ファイル|必須列|
|---|---|
|`data/mortality_pricing.csv`|`age`, `q_male`, `q_female`|
|`data/mortality_actual.csv`|`age`, `q_male`, `q_female`|
|`data/spot_curve_actual.csv`|`t`, `spot_rate`|
|`data/company_expense.csv`|`year`, `new_policies`, `inforce_avg`, `premium_income`, `acq_var_total`, `acq_fixed_total`, `maint_var_total`, `maint_fixed_total`, `coll_var_total`, `overhead_total`|

重要:
- 会社費用モデルで負値前提（planned expense）が出るとエラーで停止します。

---

## 8. コードを理解するための読み順

初学者にはこの順番を推奨します。

1. `src/pricing/cli.py`
- どのコマンドがどの関数に飛ぶかを把握

2. `src/pricing/endowment.py`
- 純保険料率・総保険料率の基本式を確認

3. `src/pricing/profit_test.py`
- 年度ごとのキャッシュフローがどう作られるかを追う

4. `src/pricing/optimize.py`
- 制約判定と係数探索ロジックを読む

5. `src/pricing/diagnostics.py`
- run_summaryの項目定義を把握

6. `src/pricing/report_feasibility.py` と `src/pricing/report_executive_pptx.py`
- レポート生成の最終段を見る

---

## 9. コア数式（コード対応）

### 9.1 loading関数
`src/pricing/endowment.py:calc_loading_parameters`

- `alpha = a0 + a_age*(issue_age-30) + a_term*(term_years-10) + a_sex*sex_indicator`
- `beta  = b0 + b_age*(issue_age-30) + b_term*(term_years-10) + b_sex*sex_indicator`
- `gamma = clamp(g0 + g_term*(term_years-10), 0.0, 0.5)`

### 9.2 保険料率
`src/pricing/endowment.py:calc_endowment_premiums`

- `net_rate = A / a`
- `gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)`

### 9.3 主要指標
`src/pricing/profit_test.py`

- `IRR = irr(net_cf series)`
- `NBV = sum(pv_net_cf)`
- `loading_surplus = pv_loading - pv_expense`
- `premium_to_maturity = (gross_annual_premium * premium_paying_years) / sum_assured`

---

## 10. 出力ファイルの見方

|ファイル|見どころ|
|---|---|
|`out/run_summary.json`|制約違反・モデルポイント別メトリクス・入力ファイルハッシュ|
|`out/result_*.xlsx`|年度キャッシュフローとサマリ|
|`out/result_*.log`|CLI向け要約ログ|
|`out/feasibility_deck*.yaml`|掃引結果と制約状況のデータデッキ|
|`reports/feasibility_report.md`|説明責任向け本文（式・係数・中間計算）|
|`reports/executive_pricing_deck.pptx`|経営層向けスライド|
|`reports/executive_pricing_deck_preview.html`|HTML/CSSプレビュー（見た目確認用）|
|`out/executive_deck_spec.json`|PPT生成の中間仕様（`trace_map`、`management_narrative`、`main_slide_checks` を含む）|
|`out/executive_deck_quality.json`|品質ゲート結果（trace/editability/runtime + explainability + main narrative checks）|
|`out/explainability_report.json`|因果チェーン、橋渡し分解、感応度分解、Pro/Conの監査向けJSON|
|`out/decision_compare.json`|推奨案/対向案の差分、採否理由、独立最適化の整合性判定|

---

## 11. よくあるつまずき

### Q1. `ModuleNotFoundError` が出る
- 仮想環境を有効化して `pip install -e .` を再実行

### Q1-2. PptxGenJS で Node 関連エラーが出る
- `npm --prefix tools/exec_deck_hybrid install` を実行
- `node -v` でNodeがPATHにあるか確認

### Q2. CSVが見つからない
- `configs/*.yaml` の相対パスが正しいか確認

### Q3. `violation_count` が下がらない
- `out/run_summary.json` の `violations` でどの制約が支配的か確認
- `propose-change` で1つずつ影響を試す

### Q4. 実行場所によって結果が変わる
- 現在は設定ファイル基準でパス解決するため、`cwd`依存は基本的に解消済み

### Q5. `test_against_excel` が失敗する
- 直近実行では `tests/test_against_excel.py::test_profit_test_against_excel` が1件失敗（IRR期待値差分）
- これはPPTX生成経路ではなく、Excel比較前提との差分の可能性が高い
- 実運用では `run_summary` / `manifest` / `quality` を監査基準にして、Excel期待値は別途キャリブレーションする

---

## 12. 開発者向けメモ

- 速く探すなら `rg` を使う
- 変更後は `python -m pytest -q`
- 文字コード健全性チェックは `python scripts/check_utf8_encoding.py --root .`
- 既存の運用ルールは `AGENTS.md` を参照

---

## 13. 免責

本リポジトリは学習・検証目的です。  
データや前提は実務利用前に必ず社内ルールと実データで再検証してください。
