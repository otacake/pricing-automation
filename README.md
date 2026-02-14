# Pricing Automation (Beginner Guide)

このリポジトリは、**養老保険のプライシングを再現可能に実行するための学習用プロジェクト**です。  
YAML設定 + CSVデータを入力にして、以下を行います。

- 保険料計算
- 年度別キャッシュフロー計算
- IRR / NBV / 制約評価
- loading係数の最適化
- 実現可能性レポート生成
- 経営層向けPPTX生成

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
  - 既定は日本語出力（`--lang en` で英語に切替可）

---

## 2. 5分で動かす

前提:
- Python 3.11+
- PowerShell

### 2.1 セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
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
python -m pricing.cli report-executive-pptx configs\trial-001.executive.optimized.yaml --lang ja
```

生成物（既定）:
- `reports/feasibility_report.md`
- `reports/executive_pricing_deck.pptx`
- `out/run_summary_executive.json`
- `out/feasibility_deck_executive.yaml`
- `out/charts/executive/*.png`

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
python -m pricing.cli report-executive-pptx configs\trial-001.executive.optimized.yaml --lang ja
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
  --lang ja
```

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

---

## 11. よくあるつまずき

### Q1. `ModuleNotFoundError` が出る
- 仮想環境を有効化して `pip install -e .` を再実行

### Q2. CSVが見つからない
- `configs/*.yaml` の相対パスが正しいか確認

### Q3. `violation_count` が下がらない
- `out/run_summary.json` の `violations` でどの制約が支配的か確認
- `propose-change` で1つずつ影響を試す

### Q4. 実行場所によって結果が変わる
- 現在は設定ファイル基準でパス解決するため、`cwd`依存は基本的に解消済み

---

## 12. 開発者向けメモ

- 速く探すなら `rg` を使う
- 変更後は `python -m pytest -q`
- 既存の運用ルールは `AGENTS.md` を参照

---

## 13. 免責

本リポジトリは学習・検証目的です。  
データや前提は実務利用前に必ず社内ルールと実データで再検証してください。
