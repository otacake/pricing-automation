from __future__ import annotations  # 型注釈の前方参照を許可し、循環参照を避けるため

import sys  # モジュール探索パスを調整するため
from pathlib import Path  # パス操作をOS非依存で行うため

import pandas as pd  # テスト用のDataFrame作成に使うため

REPO_ROOT = Path(__file__).resolve().parents[1]  # リポジトリルートを取得する
SRC_ROOT = REPO_ROOT / "src"  # src配下をモジュール探索対象にする
if str(SRC_ROOT) not in sys.path:  # まだ追加されていない場合
    sys.path.insert(0, str(SRC_ROOT))  # 先頭に追加して優先度を上げる

from pricing.cli import _format_run_output  # 出力整形の挙動を検証するため
from pricing.endowment import EndowmentPremiums, LoadingParameters  # ダミー結果の作成に使うため
from pricing.optimize import optimize_loading_parameters  # 監視対象の除外判定を検証するため
from pricing.profit_test import ModelPoint, ProfitTestBatchResult, ProfitTestResult  # ダミー結果を作るため


def _make_result(  # テスト用のProfitTestResultを作る補助関数
    model_point_id: str,  # モデルポイントID
    irr: float,  # IRR
    nbv: float,  # NBV
    loading_surplus: float,  # 充足額
    premium_to_maturity_ratio: float,  # PTM比率
) -> ProfitTestResult:  # ダミー結果を返す
    point = ModelPoint(  # ダミーモデルポイントを作る
        model_point_id=model_point_id,  # ID
        issue_age=30,  # 年齢
        sex="male",  # 性別
        term_years=10,  # 期間
        premium_paying_years=10,  # 払込期間
        sum_assured=1_000_000,  # 保険金額
    )  # モデルポイント
    loadings = LoadingParameters(alpha=0.001, beta=0.0, gamma=0.0)  # ダミーのloading
    premiums = EndowmentPremiums(  # ダミーの保険料計算結果
        A=1.0,  # A
        a=1.0,  # a
        net_rate=0.1,  # 純保険料率
        gross_rate=0.12,  # 総保険料率
        net_annual_premium=100,  # 純保険料
        gross_annual_premium=120,  # 総保険料
        monthly_premium=10,  # 月払
    )  # 保険料結果
    cashflow = pd.DataFrame({"net_cf": [0.0]})  # ダミーのキャッシュフロー
    return ProfitTestResult(  # テスト用結果を返す
        model_point=point,  # モデルポイント
        loadings=loadings,  # loading
        cashflow=cashflow,  # キャッシュフロー
        irr=irr,  # IRR
        new_business_value=nbv,  # NBV
        premiums=premiums,  # 保険料結果
        pv_loading=0.0,  # loading現価
        pv_expense=0.0,  # 費用現価
        loading_surplus=loading_surplus,  # 充足額
        premium_total=1000.0,  # 総払込
        premium_to_maturity_ratio=premium_to_maturity_ratio,  # PTM比率
    )  # 結果を返す


def test_watch_model_point_excluded_from_success(monkeypatch, tmp_path: Path) -> None:  # watch対象が成功判定から除外されるか検証する
    config = {  # 最小構成の設定を用意する
        "optimization": {  # 最適化設定
            "stages": [{"name": "base", "variables": ["a0"]}],  # ステージ定義
            "max_iterations_per_stage": 1,  # 反復回数上限
            "watch_model_point_ids": ["watch_me"],  # 監視対象
        }  # 最適化設定
    }  # 設定ここまで

    def fake_run_profit_test(_config, base_dir=None, loading_params=None):  # profit_testを偽装する
        res_ok = _make_result(  # 合格モデルポイント
            model_point_id="ok",  # ID
            irr=0.1,  # IRR
            nbv=1.0,  # NBV
            loading_surplus=100.0,  # 充足額
            premium_to_maturity_ratio=1.0,  # PTM比率
        )  # 結果
        res_watch = _make_result(  # 監視モデルポイント
            model_point_id="watch_me",  # ID
            irr=-0.5,  # IRR
            nbv=-1.0,  # NBV
            loading_surplus=-100.0,  # 充足額
            premium_to_maturity_ratio=2.0,  # PTM比率
        )  # 結果
        summary = pd.DataFrame(  # サマリを作成する
            [
                {
                    "model_point": "ok",  # ラベル
                    "sum_assured": 1_000_000,  # 保険金額
                    "irr": res_ok.irr,  # IRR
                    "new_business_value": res_ok.new_business_value,  # NBV
                    "loading_surplus": res_ok.loading_surplus,  # 充足額
                    "premium_to_maturity_ratio": res_ok.premium_to_maturity_ratio,  # PTM比率
                },
                {
                    "model_point": "watch_me",  # ラベル
                    "sum_assured": 1_000_000,  # 保険金額
                    "irr": res_watch.irr,  # IRR
                    "new_business_value": res_watch.new_business_value,  # NBV
                    "loading_surplus": res_watch.loading_surplus,  # 充足額
                    "premium_to_maturity_ratio": res_watch.premium_to_maturity_ratio,  # PTM比率
                },
            ]
        )  # サマリ
        return ProfitTestBatchResult(  # バッチ結果を返す
            results=[res_ok, res_watch],  # 個別結果
            summary=summary,  # サマリ
            expense_assumptions=None,  # 会社費用前提なし
        )  # バッチ結果

    monkeypatch.setattr("pricing.optimize.run_profit_test", fake_run_profit_test)  # profit_testを偽装する

    result = optimize_loading_parameters(config, base_dir=tmp_path)  # 最適化を実行する
    assert result.success is True  # 監視対象が除外されて成功となることを確認する
    assert result.watch_model_points == ["watch_me"]  # 監視対象が保持されることを確認する


def test_run_output_marks_watch() -> None:  # run出力でwatchが表示されるか検証する
    config = {  # 監視対象を設定する
        "optimization": {"watch_model_point_ids": ["watch_me"]},  # 監視対象の設定
    }  # 設定ここまで

    res_ok = _make_result(  # 合格モデルポイント
        model_point_id="ok",  # ID
        irr=0.1,  # IRR
        nbv=1.0,  # NBV
        loading_surplus=100.0,  # 充足額
        premium_to_maturity_ratio=1.0,  # PTM比率
    )  # 結果
    res_watch = _make_result(  # 監視モデルポイント
        model_point_id="watch_me",  # ID
        irr=-0.5,  # IRR
        nbv=-1.0,  # NBV
        loading_surplus=-100.0,  # 充足額
        premium_to_maturity_ratio=2.0,  # PTM比率
    )  # 結果
    summary = pd.DataFrame(  # サマリを作成する
        [
            {
                "model_point": "ok",  # ラベル
                "sum_assured": 1_000_000,  # 保険金額
                "irr": res_ok.irr,  # IRR
                "new_business_value": res_ok.new_business_value,  # NBV
                "loading_surplus": res_ok.loading_surplus,  # 充足額
                "premium_to_maturity_ratio": res_ok.premium_to_maturity_ratio,  # PTM比率
            },
            {
                "model_point": "watch_me",  # ラベル
                "sum_assured": 1_000_000,  # 保険金額
                "irr": res_watch.irr,  # IRR
                "new_business_value": res_watch.new_business_value,  # NBV
                "loading_surplus": res_watch.loading_surplus,  # 充足額
                "premium_to_maturity_ratio": res_watch.premium_to_maturity_ratio,  # PTM比率
            },
        ]
    )  # サマリ
    batch = ProfitTestBatchResult(  # バッチ結果を作成する
        results=[res_ok, res_watch],  # 個別結果
        summary=summary,  # サマリ
        expense_assumptions=None,  # 会社費用前提なし
    )  # バッチ結果

    output = _format_run_output(config, batch)  # 出力整形を実行する
    assert "watch_me" in output  # 監視ラベルが含まれることを確認する
    assert "status=watch" in output  # watchステータスが含まれることを確認する
