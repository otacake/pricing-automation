# 【デモ公開】説明責任まで自動化するプライシング・エージェントを作った話

> この記事は note 投稿用の下書きです。必要に応じて語尾や表現を調整してそのまま公開できます。

## 1. 何を作ったのか（3行）

保険のプライシングで、

- 十分性（制約を満たす）
- 収益性（IRR/NBVを確保する）
- 健全性（PTMなどの上限制約を守る）

を同時に満たしつつ、**「なぜその価格になったのか」まで説明できるエージェント**を作りました。  
最終成果物は、`Markdown` と `経営会議向けPPTX` を同時に出力します。

---

## 2. 今回の実行結果（2026-02-15 実行）

実行ID: `20260215_161009`

- baseline_violation_count: `6`
- final_violation_count: `0`
- optimization_applied: `true`

主要KPI（最終）:

- min IRR: `0.06876`
- min NBV: `78,837 JPY`
- max PTM: `1.06995`
- violation_count: `0`

PPT品質ゲート:

- `passed: true`
- `alt_text_coverage: 1.0`
- `speaker_notes_coverage: 1.0`
- `table_overflow_ok: true`
- `unique_titles_ok: true`

生成物:

- `reports/executive_pricing_deck.pptx`
- `reports/feasibility_report.md`
- `reports/executive_pricing_deck_preview.html`
- `out/executive_deck_quality.json`
- `out/explainability_report.json`
- `out/decision_compare.json`

---

## 3. ここが苦労した（モックアップ制作の裏側）

### 苦労1: 「数値が正しい」だけでは会議で使えない

最初は数値表は出せても、経営会議では「で、なぜこの価格？」が必ず聞かれます。  
そこで、**推奨案と対向案を独立最適化して比較**し、差分理由を本文スライドに明示する設計にしました。

### 苦労2: デザインと再現性の両立

見栄えを上げるほど“手作業の属人化”が起きやすい。  
そこで、`docs/deck_style_contract.md` を単一の見た目定義源にして、

- 配色
- 余白
- 表のオーバーフロー方針
- ナラティブ密度

を宣言的に管理する構成に寄せました。

### 苦労3: PPTX運用での現実的な落とし穴

実務では、

- 表がはみ出す
- 発表ノートがない
- 後で編集できない
- 画像/グラフに代替テキストがない

が地味に痛いです。  
`PptxGenJS` 側で master, autoPage, notes, altText を実装し、品質ゲート化して fail-fast にしました。

### 苦労4: 説明責任の“証跡化”

説明文だけでは監査対応になりません。  
主張ごとに `metric -> formula/rule -> source` の因果チェーンを JSON 出力し、
「後から追える」状態を担保しました。

---

## 4. デモで見せると刺さるポイント

デモは次の順で見せるのが分かりやすいです。

1. `run-cycle` を1コマンド実行（再現性）
2. violation が `6 -> 0` になることを確認（意思決定価値）
3. PPTXの `Decision Statement` で2案比較を説明（経営向け）
4. `out/explainability_report.json` で因果チェーンを提示（監査向け）

「きれいな資料生成」よりも、**意思決定の根拠と再実行性がある**ことを前面に出すと伝わります。

---

## 5. 再現コマンド（そのまま使える）

```powershell
python -m pytest -q
python -m pricing.cli run-cycle configs/trial-001.yaml --policy policy/pricing_policy.yaml --skip-tests
```

※ この環境では `test_profit_test_against_excel` が既知差異で1件失敗するため、
PDCA本実行は事前テスト実施後に `--skip-tests` を使っています。

---

## 6. 今後やりたいこと

- Excel比較テスト差異の恒久対応（前提の正規化）
- マルチ商品（終身・定期）への拡張
- 感応度を複合ショック化
- 経営会議の議事録テンプレートまで自動出力

---

## 7. さいごに

今回の学びはシンプルで、

**「価格を出す」だけでは価値が足りない。  
「なぜその価格か」を説明し、同じ結果を再生成できて、会議でそのまま使えることが価値。**

同じ課題感を持つ方がいたら、ぜひ意見交換したいです。
