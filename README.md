# Pricing Automation

養老保険の保険料計算と収益性検証を行うPythonプロジェクトです。契約条件、死亡率、金利、事業費を設定し、モデルポイントごとの保険料と年度別キャッシュフローを計算します。付加保険料の係数探索、候補の採否判定、説明資料の作成も行います。

設定はYAML Ain't Markup Language（YAML）形式、死亡率などの数値データはComma-Separated Values（CSV）形式で入力します。実データはリポジトリに含めていませんが、同じ列構成の合成データを用意しているため、実データなしで計算と探索を試せます。

収益性はInternal Rate of Return（IRR、内部収益率）とNew Business Value（NBV、新契約価値）で評価します。制約には、付加保険料と事業費の現価差額やPremium-to-Maturity（PTM、払込保険料総額と満期保険金の比率）も使います。制約違反が残る場合でも処理が正常終了することがあるため、実行結果と制約の達成状況は分けて確認します。

## 合成データで試す

計算と探索にはPython 3.11以上が必要です。PowerPointの生成にはNode.js 20以上とPptxGenJSを追加で用意します。以下のコマンドはリポジトリのルートで実行します。

### 環境を用意する

WindowsのPowerShellでは、仮想環境を作って有効化し、プロジェクトとテスト用のpytestをインストールします。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install pytest
```

macOSやLinuxでは、仮想環境を有効化するコマンドを`source .venv/bin/activate`に置き換え、以降は同じ手順で実行します。

### テストと入力検証を実行する

```powershell
python -m pytest -q
python -m pricing.cli validate-data configs/trial-001.synthetic.yaml
```

合成データは`tests/fixtures/data/`にあり、`configs/trial-001.synthetic.yaml`から参照します。入力検証が通ると`validate_data: ok`が表示されます。非推奨の設定キーについて警告が出ても、検証エラーがなければ終了コードは0です。

実データがない環境では、実データや比較用Excelブックを使うテストをスキップします。2026年10月6日にマージ後のコードで確認した結果は、118件成功、5件スキップでした。実データとの一致は、合成データのテストとは別に確認する必要があります。

### 係数探索を実行する

```powershell
python -m pricing.cli pdca-loop configs/trial-001.synthetic.yaml --policy policy/pricing_policy.yaml
```

現在の設定から付加保険料の係数を探索し、改善した候補だけを採用します。処理を繰り返す回数の既定値は3回ですが、候補を不採用にした時点で終了します。回数を指定する場合は`--max-iterations 1`などを付けます。

2026年10月6日の確認では、1回目の候補を不採用にして元の設定を保持し、以下の結果で正常終了しました。

```text
status: success
stop_reason: lexicographic_objective_worse
gate_passed: false
final_violation_count: 6
gate_max_violation_count: 0
iterations_run: 1
```

`status: success`は処理の正常終了を表します。制約達成の判定は`gate_passed`に記録され、この実行では違反6件が残っています。終了コード0だけで制約を達成したとは判断できません。

## 探索と資料作成の使い分け

Plan–Do–Check–Act（PDCA）に対応するコマンドは、係数探索を繰り返す`pdca-loop`と、計算から資料作成までを一度に行う`run-cycle`です。両者の処理範囲は異なります。

| 処理 | `pdca-loop` | `run-cycle` |
|---|---|---|
| テスト | コマンド内では実行しない。事前に実行する | 既定でpytestを実行する |
| 入力検証 | 計算前に実行する | 計算前に実行する |
| 係数探索 | 候補を採用する限り、設定した回数まで繰り返す | 初期計算の違反件数がポリシーの上限を超える場合に1回試す |
| 採否判定 | 現在の設定と候補を比較する | 現在の設定と候補を比較する |
| 資料作成 | 実行しない | ポリシーに従って説明文書とPowerPointを作成する |

### 候補の採否

`pdca-loop`と`run-cycle`では、次の順で候補と現在の設定を比較します。先の項目に差があれば、後の項目では判断を覆しません。

1. 制約違反の件数が少ない。
2. 違反件数が同じなら、比較対象のモデルポイントの最小IRRが高い。
3. 最小IRRも同じなら、比較対象の年払保険料の合計が小さい。

IRRの差は`1e-8`、保険料の差は`1e-4`以内なら同じと扱います。全項目が同じ候補は採用しません。違反件数は違反したモデルポイント数ではなく、違反した制約の数です。

`optimization.watch_model_point_ids`に指定したモデルポイントは、違反件数と通常のIRR、保険料の比較から除外します。ただし、すべてのモデルポイントがwatchの場合、IRRと保険料の比較には全件を使います。watchの指標は結果に残るため、監視対象にした理由と残る違反を確認します。

比較対象のIRRまたは保険料が有限値でない候補は、`non_finite_metrics`として不採用になります。`pdca-loop`では初期設定の比較指標が有限値でない場合、処理を失敗として終了し、`gate_passed`を`null`にします。有効な設定を評価した後の処理失敗では、その設定に対する制約判定を保持します。

`optimize`単体は探索結果を設定ファイルに保存しますが、現在の設定との採否判定は行いません。改善した候補だけを保持する場合は、`pdca-loop`または`run-cycle`を使います。

### 停止理由と制約判定

`pdca-loop`の`stop_reason`には、終了した理由を記録します。

| 値 | 意味 |
|---|---|
| `no_improvement` | 比較指標が同じで、改善がない |
| `lexicographic_objective_worse` | 違反件数は同じだが、IRRまたは保険料の比較で劣る |
| `violation_count_increased` | 候補の違反件数が増えた |
| `non_finite_metrics` | 候補のIRRまたは保険料が有限値でない |
| `max_iterations` | 設定した試行回数に達した |
| `failed` | 入力検証や計算などの処理に失敗した |

`gate_passed`は、最終設定の違反件数が`gate.max_violation_count`以下かを表します。既定の上限は0件です。判定できない場合は`null`で、制約を達成したことを意味しません。制約達成だけを理由に探索を終了する処理はなく、候補の不採用または試行回数の上限で終了します。

### ポリシーと変更記録

実行方針は[`policy/pricing_policy.yaml`](policy/pricing_policy.yaml)に定義しています。

| 設定キー | 既定値と役割 |
|---|---|
| `gate.max_violation_count` | `0`。許容する違反件数の上限 |
| `loop.max_iterations` | `3`。`pdca-loop`の試行回数の上限 |
| `loop.random_seed` | `20261005`。乱数シード |
| `acceptance.objective` | `maximize_min_irr`。採否比較の目的 |
| `acceptance.tie_break` | `lower_premium`。最小IRRが同じ場合の判定 |
| `ledger.path` | `out/pdca_ledger.jsonl`。採否と未適用の変更案の追記先 |

現在対応している採否設定は、`maximize_min_irr`と`lower_premium`の組み合わせだけです。別の値を指定すると、ポリシーを読み込む段階でエラーになります。

探索で制約を満たせなかった場合、解約控除期間の延長やIRR目標の引下げを変更案として記録します。変更案は`decision: approval_required`、`applied: false`で記録するだけで、探索中に自動適用しません。

設定の比較用ハッシュ`input_config_sha256`は、最上位の`optimize_summary`だけを除いて計算します。付加保険料の係数、金利、制約、その他の設定は含まれます。設定全体のハッシュや設定ファイルのハッシュも、記録用に別途保持します。

## 実データを使う

実データ用の標準設定は`configs/trial-001.yaml`です。予定死亡率、実績死亡率、割引用スポットカーブ、会社費用の4ファイルを`data/`に用意します。`data/*.csv`はGitの追跡対象から除外しています。

| ファイル | 必須列 |
|---|---|
| `mortality_pricing.csv` | `age`, `q_male`, `q_female` |
| `mortality_actual.csv` | `age`, `q_male`, `q_female` |
| `spot_curve_actual.csv` | `t`, `spot_rate` |
| `company_expense.csv` | `year`, `new_policies`, `inforce_avg`, `premium_income`, `acq_var_total`, `acq_fixed_total`, `maint_var_total`, `maint_fixed_total`, `coll_var_total`, `overhead_total` |

入力検証では、死亡率を0以上1以下、スポット金利を年率の小数で-0.05以上0.25以下とします。死亡率の年齢は重複のない連続した非負整数、金利の年数`t`は1から始まる連続した整数で指定します。会社費用の金額は非負、新契約件数、平均保有契約件数、保険料収入は正の値が必要です。

モデルポイントの`id`には欠損、空欄、重複を認めず、`sum_assured`は正の値にします。各モデルポイントで`sum_assured`を省略した場合は、`product.sum_assured`を使います。`model_points`を指定した場合、単数形の`model_point`は計算にも入力検証にも使いません。

```powershell
python -m pricing.cli validate-data configs/trial-001.yaml
```

### 設定と相対パス

契約条件は`model_points`、予定利率は`pricing.interest.flat_rate`、収益性検証の前提は`profit_test`、制約と探索方法は`optimization`で指定します。付加保険料は固定の`loading_alpha_beta_gamma`か、年齢、期間、性別で変化する`loading_parameters`を使います。両方がある場合は`loading_parameters`を優先します。

入力と出力の相対パスは、設定ファイルから上位に探して最初に見つかった`pyproject.toml`のあるディレクトリを基準にします。リポジトリ内の設定なら、基準はリポジトリのルートです。`pyproject.toml`が見つからない場合は、設定ファイルのあるディレクトリを使います。

`run`や`optimize`単体の出力先は`outputs`で指定します。同じ出力先を使うと以前の結果を上書きするため、手動実行を保存する場合は日時を含むファイル名にします。`pdca-loop`と`run-cycle`は、実行識別子を含む出力先を自動で作ります。

## 計算から資料作成まで実行する

PowerPointを作成する場合は、Node.jsを用意して描画用の依存パッケージをインストールします。

```powershell
npm --prefix tools/exec_deck_hybrid install
python -m pricing.cli run-cycle configs/trial-001.yaml --policy policy/pricing_policy.yaml
```

`run-cycle`はテスト、入力検証、初期計算、必要な場合の係数探索、採否比較、最終結果の保存、資料作成を順に実行します。既定のポリシーでは、実現可能性の分析、説明文書、PowerPoint、ブラウザー用プレビューを生成します。係数探索だけを試す場合は、先に示した合成データの`pdca-loop`で十分です。

PowerPointの生成にはPptxGenJSを使います。既定のテーマは`consulting-clean-v2`、本文とグラフの言語はそれぞれ日本語と英語です。本文9枚は結論、根拠、リスク、意思決定要請の順に記述し、`Decision Statement`で推奨案と対向案を比較します。色、余白、フォント、本文の構成は[`docs/deck_style_contract.md`](docs/deck_style_contract.md)で定義しています。

最終結果の保存後も、資料生成の品質検査で失敗する場合があります。失敗した段階を`failed_stage`、失敗の分類を`failure_class`として実行記録と結果ログに残します。正常終了時も制約違反が残る場合があるため、`run-cycle`では最終サマリの違反件数を確認します。

## 個別コマンド

Command Line Interface（CLI）の入口は`python -m pricing.cli`です。各コマンドの引数は`python -m pricing.cli <command> --help`で確認できます。

| コマンド | 処理 |
|---|---|
| `validate-data <config>` | 設定と入力データを検証する |
| `run <config>` | 保険料と収益性を計算し、Excel、ログ、構造化サマリを保存する |
| `optimize <config>` | 付加保険料の係数を探索し、結果を設定ファイルに保存する |
| `pdca-loop <config> --policy <policy>` | 候補を比較し、改善した設定を保持しながら探索を繰り返す |
| `run-cycle <config> --policy <policy>` | テストから資料作成までを一度に実行する |
| `propose-change <config> --set <key=value> --reason <text>` | 元の設定を変更せずに、変更前後の計算結果を比較する |
| `sweep-ptm <config> --all-model-points` | PTMを変えて収益性と制約の達成状況を調べる |
| `report-feasibility <config>` | 実現可能性の分析結果をYAML形式で保存する |
| `report-executive-pptx <config>` | 説明文書とPowerPointを生成する |

`optimize`の設定保存先を`outputs.optimized_config_path`で指定しない場合、入力ファイル名に`.optimized`を付けて保存します。保存されたことだけでは制約達成や改善を意味しないため、再計算して指標を確認します。

PTMの分析範囲は`--start`、`--end`、`--step`、対象の限定は`--model-point`で指定します。設定変更の比較には`propose-change`の`--set`を使い、複数の変更は`--set`を繰り返して指定します。

資料だけを作る場合は、次のコマンドを使います。既定で2案比較と説明内容の検査を有効にしています。

```powershell
python -m pricing.cli report-executive-pptx configs/trial-001.executive.optimized.yaml `
  --theme consulting-clean-v2 `
  --style-contract docs/deck_style_contract.md `
  --decision-compare on `
  --counter-objective maximize_min_irr `
  --explainability-strict `
  --lang ja --chart-lang en
```

既存の`configs/*.optimized.yaml`は保存済みの設定です。現在の入力に対する探索結果が必要なら、対象の設定で探索をやり直します。

## 計算式と出力の読み方

### 付加保険料と保険料率

付加保険料の係数は、加入年齢、保険期間、性別から次のように求めます。`sex_indicator`は女性が1、男性が0で、`gamma`は0以上0.5以下に制限します。

```text
alpha = a0 + a_age * (issue_age - 30) + a_term * (term_years - 10) + a_sex * sex_indicator
beta  = b0 + b_age * (issue_age - 30) + b_term * (term_years - 10) + b_sex * sex_indicator
gamma = min(max(g0 + g_term * (term_years - 10), 0.0), 0.5)

net_rate   = A / a
gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)
```

`A`は給付現価係数、`a`は保険料払込期間に対応する年金現価係数です。年払保険料は保険料率に保険金額を掛け、円単位に丸めます。計算は[`src/pricing/endowment.py`](src/pricing/endowment.py)で行います。

IRRは年度別の純キャッシュフローから求め、NBVは純キャッシュフローの割引現価を合計します。`loading_surplus`は付加保険料現価から事業費現価を引いた金額、PTMは年払保険料に払込年数を掛け、保険金額で割った値です。計算と年度別の内訳は[`src/pricing/profit_test.py`](src/pricing/profit_test.py)で確認できます。

### 保存する結果

計算結果や実行記録はJavaScript Object Notation（JSON）形式でも保存します。探索の採否記録`pdca_ledger.jsonl`は、1行ごとにJSON形式の記録を追記するファイルです。

| 出力先 | 内容 |
|---|---|
| `out/run_summary*.json` | モデルポイント別の指標、制約の判定、違反の内訳 |
| `out/result_*.xlsx` | 年度別キャッシュフローとサマリ |
| `out/result_*.log` | 計算結果や処理失敗の記録 |
| `out/run_manifest_<id>.json` | 設定、ハッシュ、コマンド、シード、実行結果、出力先 |
| `out/pdca_ledger.jsonl` | 候補の採否、比較指標、未適用の変更案。場所はポリシーで変更可能 |
| `out/pdca_loop_<id>/champion.yaml` | `pdca-loop`で最終的に保持した設定 |
| `out/pdca_loop_<id>/iter_<n>/candidate.yaml` | 各試行で評価した候補の設定 |
| `out/feasibility_deck*.yaml` | PTMを変えた分析結果と制約の判定 |
| `reports/feasibility_report*.md` | 計算式、係数、途中計算、感度分析を含む説明文書 |
| `reports/executive_pricing_deck*.pptx` | 経営層向けのスライド |
| `reports/executive_pricing_deck_preview*.html` | ブラウザーで確認するプレビュー |
| `out/executive_deck_spec*.json` | スライドの内容と数値の参照元 |
| `out/executive_deck_quality*.json` | 数値の参照、編集可能性、本文構成などの品質判定 |
| `out/explainability_report*.json`, `out/decision_compare*.json` | 説明内容と2案比較の検査結果 |

`pdca-loop`が正常終了すると、最終的に保持した設定を`champion.yaml`に保存します。途中で失敗した場合は、初期設定を評価できていても`champion.yaml`が生成されないことがあります。失敗時はまず実行記録の`status`、`failed_stage`、`failure_class`を確認します。

## コードと運用ルール

コマンドから計算を追う場合は、[`src/pricing/cli.py`](src/pricing/cli.py)、[`src/pricing/endowment.py`](src/pricing/endowment.py)、[`src/pricing/profit_test.py`](src/pricing/profit_test.py)の順に読むと、入力、保険料、キャッシュフローの対応を確認できます。探索は[`src/pricing/optimize.py`](src/pricing/optimize.py)、採否判定は[`src/pricing/acceptance.py`](src/pricing/acceptance.py)、反復処理は[`src/pricing/pdca_loop.py`](src/pricing/pdca_loop.py)にあります。

全体のファイル関係は[`docs/script_relationships.md`](docs/script_relationships.md)、運用ルールは[`AGENTS.md`](AGENTS.md)を参照します。計算、探索、資料作成の前にテストを実行し、負の予定事業費がある入力はエラーとして停止します。文字コードの検査は`python scripts/check_utf8_encoding.py --root .`で実行します。

### 実行時に確認する点

Pythonのモジュールが見つからない場合は、仮想環境を有効にして`python -m pip install -e .`を実行します。pytestも別途インストールします。PowerPoint生成でNode.jsやPptxGenJSが見つからない場合は、`node -v`と描画用パッケージのインストールを確認します。

入力ファイルが見つからない場合は、設定の参照先と相対パスの基準を確認します。初回の計算確認には、実データを要求する`trial-001.yaml`より、リポジトリ内のデータを参照する`trial-001.synthetic.yaml`を使います。

`report-executive-pptx`の`--engine`は廃止されています。`tasks.ps1`の`executive`には古い`--engine`指定が残っているため、資料作成には上記のコマンドを直接使います。旧ポリシーの`reporting.pptx_engine: legacy`はエラーになり、`html_hybrid`は互換入力として読み飛ばします。

本プロジェクトは学習と検証を目的としています。実務で使用する場合は、社内ルールと実データに照らして計算結果と前提を再検証してください。
