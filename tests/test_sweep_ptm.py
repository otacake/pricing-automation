from __future__ import annotations  # 型注釈の前方参照を許可し、循環参照を避けるため

import sys  # モジュール探索パスを調整するため
from pathlib import Path  # パス操作をOS非依存で行うため

import pytest  # テスト実行と例外検証に使うため
import yaml  # YAML設定を読み込むため

REPO_ROOT = Path(__file__).resolve().parents[1]  # リポジトリルートを取得する
SRC_ROOT = REPO_ROOT / "src"  # src配下をモジュール探索対象にする
if str(SRC_ROOT) not in sys.path:  # まだ追加されていない場合
    sys.path.insert(0, str(SRC_ROOT))  # 先頭に追加して優先度を上げる

from pricing.sweep_ptm import load_model_points, sweep_premium_to_maturity, sweep_premium_to_maturity_all  # 対象関数をテストするため


def test_sweep_ptm_outputs_rows_and_no_nan(tmp_path: Path) -> None:  # 単一モデルポイントのスイープ結果を検証する
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"  # テスト用設定パス
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))  # 設定を読み込む

    label = "male_age30_term35"  # 対象モデルポイントのラベル
    start = 1.0  # スイープ開始値
    end = 1.02  # スイープ終了値
    step = 0.01  # スイープ刻み

    out_path = tmp_path / "sweep.csv"  # 出力先の一時パス
    df, _ = sweep_premium_to_maturity(  # スイープを実行する
        config=config,  # 設定
        base_dir=REPO_ROOT,  # 相対パス基準
        model_point_label=label,  # 対象ラベル
        start=start,  # 開始値
        end=end,  # 終了値
        step=step,  # 刻み
        irr_threshold=0.0,  # IRR閾値
        out_path=out_path,  # 出力先
    )  # 実行結果を受け取る

    expected_rows = int(round((end - start) / step)) + 1  # 期待される行数を計算する
    assert len(df) == expected_rows  # 行数が一致することを検証する
    assert not df.isna().any().any()  # NaNが含まれないことを検証する

    sum_assured = 3000000  # 保険金額
    premium_paying_years = 35  # 払込期間
    for row in df.itertuples(index=False):  # 各行の保険料計算を検証する
        expected = int(round(row.r * sum_assured / premium_paying_years, 0))  # 期待される年払保険料
        assert row.gross_annual_premium == expected  # 計算が一致することを確認する


def test_sweep_ptm_invalid_model_point() -> None:  # 不正なモデルポイント指定時の挙動を検証する
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"  # テスト用設定パス
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))  # 設定を読み込む

    with pytest.raises(ValueError):  # ValueErrorが発生することを期待する
        sweep_premium_to_maturity(  # 存在しないモデルポイントで実行する
            config=config,  # 設定
            base_dir=REPO_ROOT,  # 相対パス基準
            model_point_label="unknown_point",  # 存在しないラベル
            start=1.0,  # 開始値
            end=1.01,  # 終了値
            step=0.01,  # 刻み
            irr_threshold=0.0,  # IRR閾値
            out_path=REPO_ROOT / "out" / "tmp.csv",  # 出力先
        )  # 例外を期待する


def test_sweep_ptm_all_model_points_rows(tmp_path: Path) -> None:  # 全モデルポイントのスイープ行数を検証する
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"  # テスト用設定パス
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))  # 設定を読み込む
    points = load_model_points(config)  # モデルポイント一覧を取得する

    out_path = tmp_path / "all.csv"  # 出力先の一時パス
    df, _ = sweep_premium_to_maturity_all(  # 全モデルポイントをスイープする
        config=config,  # 設定
        base_dir=REPO_ROOT,  # 相対パス基準
        start=1.0,  # 開始値
        end=1.02,  # 終了値
        step=0.01,  # 刻み
        irr_threshold=0.0,  # IRR閾値
        nbv_threshold=0.0,  # NBV閾値
        loading_surplus_ratio_threshold=-1.0,  # 充足比率閾値
        premium_to_maturity_hard_max=2.0,  # PTM上限
        out_path=out_path,  # 出力先
    )  # 実行結果を受け取る

    expected_rows = len(points) * 3  # モデルポイント数×スイープ数
    assert len(df) == expected_rows  # 行数が一致することを検証する


def test_sweep_ptm_all_model_points_not_found(tmp_path: Path) -> None:  # 最小rが見つからない条件を検証する
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"  # テスト用設定パス
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))  # 設定を読み込む

    out_path = tmp_path / "all.csv"  # 出力先の一時パス
    _, min_r_by_id = sweep_premium_to_maturity_all(  # 条件を厳しくして実行する
        config=config,  # 設定
        base_dir=REPO_ROOT,  # 相対パス基準
        start=1.0,  # 開始値
        end=1.01,  # 終了値
        step=0.01,  # 刻み
        irr_threshold=1.0,  # 高すぎるIRR閾値
        nbv_threshold=1e12,  # 高すぎるNBV閾値
        loading_surplus_ratio_threshold=1.0,  # 高すぎる充足比率閾値
        premium_to_maturity_hard_max=1.0,  # 厳しいPTM上限
        out_path=out_path,  # 出力先
    )  # 実行結果を受け取る

    assert all(value is None for value in min_r_by_id.values())  # 全てNoneになることを検証する
