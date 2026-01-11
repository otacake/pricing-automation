from __future__ import annotations  # 型注釈の前方参照を許可し、循環参照を避けるため

import sys  # モジュール探索パスを調整するため
from pathlib import Path  # パス操作をOS非依存で行うため

import pandas as pd  # テスト用のDataFrame作成に使うため
import pytest  # テスト実行とモンキーパッチに使うため

REPO_ROOT = Path(__file__).resolve().parents[1]  # リポジトリルートを取得する
SRC_ROOT = REPO_ROOT / "src"  # src配下をモジュール探索対象にする
if str(SRC_ROOT) not in sys.path:  # まだ追加されていない場合
    sys.path.insert(0, str(SRC_ROOT))  # 先頭に追加して優先度を上げる

import pricing.optimize as optimize_mod  # 最適化モジュールをテストするため
from pricing.endowment import EndowmentPremiums, LoadingParameters  # ダミー結果の作成に使うため
from pricing.outputs import write_optimize_log  # ログ出力の確認に使うため
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
    loadings = LoadingParameters(alpha=0.0, beta=0.0, gamma=0.0)  # ダミーのloading
    premiums = EndowmentPremiums(  # ダミーの保険料計算結果
        A=1.0,  # A
        a=1.0,  # a
        net_rate=0.1,  # 純保険料率
        gross_rate=0.1,  # 総保険料率
        net_annual_premium=100,  # 純保険料
        gross_annual_premium=100,  # 総保険料
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


def test_optimize_exemption_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # 免除対象がログに出るか確認する
    config = {  # 最小構成の設定を用意する
        "optimization": {  # 最適化設定
            "stages": [{"name": "base", "variables": ["a0"]}],  # ステージ定義
            "max_iterations_per_stage": 1,  # 反復回数上限
            "exemption": {  # 免除設定
                "enabled": True,  # 免除を有効化する
                "method": "sweep_ptm",  # 免除方法
                "sweep": {"start": 1.0, "end": 1.0, "step": 0.01, "irr_threshold": 0.0},  # sweep設定
            },  # 免除設定
        }  # 最適化設定
    }  # 設定ここまで

    def fake_sweep_premium_to_maturity_all(**_kwargs):  # sweepを偽装して免除対象を返す
        return pd.DataFrame(), {"mp1": 1.0, "mp2": None}  # mp2が免除対象になる

    def fake_run_profit_test(_config, base_dir=None, loading_params=None):  # profit_testを偽装する
        res1 = _make_result(  # 成功モデルポイント
            model_point_id="mp1",  # ID
            irr=0.1,  # IRR
            nbv=1.0,  # NBV
            loading_surplus=100.0,  # 充足額
            premium_to_maturity_ratio=1.0,  # PTM比率
        )  # 結果
        res2 = _make_result(  # 失敗モデルポイント
            model_point_id="mp2",  # ID
            irr=-0.5,  # IRR
            nbv=-1.0,  # NBV
            loading_surplus=-100.0,  # 充足額
            premium_to_maturity_ratio=2.0,  # PTM比率
        )  # 結果
        summary = pd.DataFrame(  # サマリを作成する
            [
                {
                    "model_point": "mp1",  # ラベル
                    "sum_assured": 1_000_000,  # 保険金額
                    "irr": res1.irr,  # IRR
                    "new_business_value": res1.new_business_value,  # NBV
                    "loading_surplus": res1.loading_surplus,  # 充足額
                    "premium_to_maturity_ratio": res1.premium_to_maturity_ratio,  # PTM比率
                },
                {
                    "model_point": "mp2",  # ラベル
                    "sum_assured": 1_000_000,  # 保険金額
                    "irr": res2.irr,  # IRR
                    "new_business_value": res2.new_business_value,  # NBV
                    "loading_surplus": res2.loading_surplus,  # 充足額
                    "premium_to_maturity_ratio": res2.premium_to_maturity_ratio,  # PTM比率
                },
            ]
        )  # サマリ
        return ProfitTestBatchResult(  # バッチ結果を返す
            results=[res1, res2],  # 個別結果
            summary=summary,  # サマリ
            expense_assumptions=None,  # 会社費用前提なし
        )  # バッチ結果

    monkeypatch.setattr(  # sweep関数を偽装する
        optimize_mod, "sweep_premium_to_maturity_all", fake_sweep_premium_to_maturity_all
    )  # 置き換え
    monkeypatch.setattr(optimize_mod, "run_profit_test", fake_run_profit_test)  # profit_testを偽装する

    result = optimize_mod.optimize_loading_parameters(config, base_dir=tmp_path)  # 最適化を実行する
    assert result.exempt_model_points == ["mp2"]  # 免除対象が正しいことを確認する
    assert result.success is True  # 成功判定がTrueであることを確認する

    log_path = tmp_path / "optimize.log"  # ログ出力先
    write_optimize_log(log_path, config, result)  # ログを書き出す
    log_text = log_path.read_text(encoding="utf-8")  # ログを読み込む
    assert "exempt_list: mp2" in log_text  # 免除対象が記録されることを確認する
    assert "exempt_detail id=mp2" in log_text  # 免除詳細が記録されることを確認する
