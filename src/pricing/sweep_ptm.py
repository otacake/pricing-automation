from __future__ import annotations  # 型注釈の前方参照を許可し、循環参照を避けるため

"""
Sweep premium-to-maturity ratios and evaluate IRR for a model point.
"""

import copy  # 設定の一部を差し替えるため
from dataclasses import dataclass  # モデルポイント情報を構造化するため
from pathlib import Path  # パスをOS非依存で扱うため
from typing import Iterable, Mapping  # 型注釈で入出力を明確にするため

import pandas as pd  # 結果テーブルを扱うため

from .profit_test import run_profit_test  # 収益性検証を共通ロジックで実行するため


@dataclass(frozen=True)  # スイープ用モデルポイントを不変で扱うため
class SweepModelPoint:  # スイープ対象のモデルポイント定義
    """
    Model point definition used in the premium-to-maturity sweep.

    Units
    - issue_age: years
    - term_years / premium_paying_years: years
    - sum_assured: JPY
    - sex: "male" / "female"
    """

    issue_age: int  # 加入年齢
    sex: str  # 性別
    term_years: int  # 保険期間
    premium_paying_years: int  # 払込期間
    sum_assured: int  # 保険金額
    model_point_id: str  # ラベル


def model_point_label(issue_age: int, sex: str, term_years: int) -> str:  # ラベル生成を共通化する
    """
    Build a model point label used in CLI selection.
    """
    return f"{sex}_age{issue_age}_term{term_years}"  # 性別・年齢・期間でラベル化する


def load_model_points(config: Mapping[str, object]) -> list[SweepModelPoint]:  # 設定からモデルポイントを読み込む
    """
    Load model points from config for sweep selection.
    """
    product = config.get("product", {}) if isinstance(config, Mapping) else {}  # 商品設定を取得する
    defaults = {  # デフォルト値を商品設定から取得する
        "term_years": product.get("term_years"),  # 保険期間
        "premium_paying_years": product.get("premium_paying_years"),  # 払込期間
        "sum_assured": product.get("sum_assured"),  # 保険金額
    }  # デフォルト値の辞書
    points_cfg = config.get("model_points")  # 複数モデルポイント設定
    if points_cfg is None:  # 複数定義が無ければ単独定義を使う
        points_cfg = [config.get("model_point")]  # 単独定義をリスト化する

    points: list[SweepModelPoint] = []  # 結果のリストを初期化する
    for entry in points_cfg or []:  # モデルポイント設定を走査する
        if not isinstance(entry, Mapping):  # dictでなければ無視する
            continue  # 次の定義へ
        issue_age = int(entry["issue_age"])  # 年齢を取得する
        sex = str(entry["sex"])  # 性別を取得する
        term_years = int(entry.get("term_years", defaults["term_years"]))  # 保険期間を取得する
        premium_paying_years = int(  # 払込期間を取得する
            entry.get("premium_paying_years", defaults["premium_paying_years"])
        )  # 払込期間の取得
        sum_assured = int(entry.get("sum_assured", defaults["sum_assured"]))  # 保険金額を取得する
        model_point_id = entry.get("id")  # モデルポイントIDを取得する
        label = (  # ラベルを決める
            str(model_point_id)
            if model_point_id is not None
            else model_point_label(issue_age, sex, term_years)
        )  # ラベルの決定
        points.append(  # モデルポイントを追加する
            SweepModelPoint(  # SweepModelPointを構築する
                issue_age=issue_age,  # 年齢
                sex=sex,  # 性別
                term_years=term_years,  # 保険期間
                premium_paying_years=premium_paying_years,  # 払込期間
                sum_assured=sum_assured,  # 保険金額
                model_point_id=label,  # ラベル
            )  # モデルポイント構築
        )  # リストに追加
    if not points:  # 定義が無い場合はエラー
        raise ValueError("Model point definition is missing.")  # 入力不備を通知する
    return points  # モデルポイント一覧を返す


def select_model_point(  # ラベルでモデルポイントを選択する
    points: Iterable[SweepModelPoint],  # モデルポイント一覧
    label: str,  # 選択したいラベル
) -> SweepModelPoint:  # 選択結果を返す
    """
    Select a model point by label for sweep.
    """
    points_list = list(points)  # イテレータをリスト化して再利用しやすくする
    for point in points_list:  # 各モデルポイントを走査する
        if point.model_point_id == label:  # ラベルが一致した場合
            return point  # 対象を返す
    raise ValueError(f"Model point not found: {label}")  # 見つからなければエラー


def _iter_range(start: float, end: float, step: float) -> list[float]:  # スイープ範囲を生成する
    if step <= 0:  # ステップが不正ならエラー
        raise ValueError("step must be positive.")  # 入力不備を通知する
    values: list[float] = []  # 結果のリストを初期化する
    current = start  # 開始値を設定する
    while current <= end + 1e-12:  # 浮動小数誤差を考慮して範囲を回す
        values.append(round(current, 10))  # 丸めた値を追加する
        current += step  # 次の値へ進める
    if not values:  # 空なら不正
        raise ValueError("Sweep range is empty.")  # 入力不備を通知する
    return values  # 値のリストを返す


def _model_point_to_entry(model_point: SweepModelPoint) -> dict[str, object]:
    return {
        "id": model_point.model_point_id,
        "issue_age": model_point.issue_age,
        "sex": model_point.sex,
        "term_years": model_point.term_years,
        "premium_paying_years": model_point.premium_paying_years,
        "sum_assured": model_point.sum_assured,
    }


def _calc_sweep_metrics(  # スイープ1点の指標を計算する
    config: Mapping[str, object],  # 設定
    base_dir: Path,  # 相対パス基準
    model_point: SweepModelPoint,  # モデルポイント
    gross_annual_premium: int,  # 総保険料（年額）
) -> dict[str, float]:  # 指標を辞書で返す
    local_config = copy.deepcopy(dict(config))
    local_config["model_points"] = [_model_point_to_entry(model_point)]
    local_config.pop("model_point", None)

    batch_result = run_profit_test(
        local_config,
        base_dir=base_dir,
        gross_annual_premium_overrides={model_point.model_point_id: gross_annual_premium},
    )
    result = batch_result.results[0]

    return {
        "irr": float(result.irr),
        "nbv": float(result.new_business_value),
        "loading_surplus": float(result.loading_surplus),
        "loading_surplus_ratio": float(
            result.loading_surplus / float(result.model_point.sum_assured)
        ),
        "premium_to_maturity": float(result.premium_to_maturity_ratio),
        "alpha": float(result.loadings.alpha),
        "beta": float(result.loadings.beta),
        "gamma": float(result.loadings.gamma),
        "loading_positive": float(
            result.premiums.gross_annual_premium - result.premiums.net_annual_premium
        ),
    }


def sweep_premium_to_maturity(  # 単一モデルポイントのスイープを実行する
    config: Mapping[str, object],  # 設定
    base_dir: Path,  # 相対パス基準
    model_point_label: str,  # 対象ラベル
    start: float,  # 開始値
    end: float,  # 終了値
    step: float,  # 刻み
    irr_threshold: float,  # IRR閾値
    out_path: Path,  # 出力先
) -> tuple[pd.DataFrame, float | None]:  # 結果と最小rを返す
    """
    Sweep premium-to-maturity ratios for a model point.

    Units
    - start/end/step: premium_to_maturity ratio
    - irr_threshold: annual rate
    - out_path: CSV output path
    """
    points = load_model_points(config)  # モデルポイント一覧を読む
    model_point = select_model_point(points, model_point_label)  # 対象モデルポイントを選ぶ

    rows: list[dict[str, float | int]] = []  # 結果行を初期化する
    min_r: float | None = None  # 最小rを初期化する

    for ratio in _iter_range(start, end, step):  # rをスイープする
        gross_annual_premium = int(  # 総保険料を計算する
            round(ratio * model_point.sum_assured / model_point.premium_paying_years, 0)
        )  # 総保険料の算出
        metrics = _calc_sweep_metrics(  # 指標を計算する
            config=config,  # 設定
            base_dir=base_dir,  # 相対パス基準
            model_point=model_point,  # モデルポイント
            gross_annual_premium=gross_annual_premium,  # 総保険料
        )  # 指標結果
        if min_r is None and metrics["irr"] >= irr_threshold:  # 初めて閾値を満たしたら記録する
            min_r = ratio  # 最小rとして保存する

        rows.append(  # 行データを追加する
            {
                "model_point_id": model_point.model_point_id,  # モデルポイントID
                "sex": model_point.sex,  # 性別
                "issue_age": model_point.issue_age,  # 年齢
                "term_years": model_point.term_years,  # 保険期間
                "premium_paying_years": model_point.premium_paying_years,  # 払込期間
                "sum_assured": model_point.sum_assured,  # 保険金額
                "r": ratio,  # PTM比率
                "gross_annual_premium": gross_annual_premium,  # 総保険料
                "irr": metrics["irr"],  # IRR
                "nbv": metrics["nbv"],  # NBV
                "loading_surplus": metrics["loading_surplus"],  # 充足額
                "loading_surplus_ratio": metrics["loading_surplus_ratio"],  # 充足比率
                "premium_to_maturity": metrics["premium_to_maturity"],  # PTM比率
            }
        )  # 行追加

    df = pd.DataFrame(rows)  # DataFrameに変換する
    out_path.parent.mkdir(parents=True, exist_ok=True)  # 出力先ディレクトリを作る
    df.to_csv(out_path, index=False)  # CSVとして保存する
    return df, min_r  # 結果と最小rを返す


def sweep_premium_to_maturity_all(  # 全モデルポイントのスイープを実行する
    config: Mapping[str, object],  # 設定
    base_dir: Path,  # 相対パス基準
    start: float,  # 開始値
    end: float,  # 終了値
    step: float,  # 刻み
    irr_threshold: float,  # IRR閾値
    nbv_threshold: float,  # NBV閾値
    loading_surplus_ratio_threshold: float,  # 充足比率閾値
    premium_to_maturity_hard_max: float,  # PTM上限
    out_path: Path,  # 出力先
) -> tuple[pd.DataFrame, dict[str, float | None]]:  # 結果と最小r辞書を返す
    """
    Sweep premium-to-maturity ratios for all model points.

    Units
    - start/end/step: premium_to_maturity ratio
    - irr_threshold: annual rate
    - nbv_threshold: JPY
    - loading_surplus_ratio_threshold: ratio
    - premium_to_maturity_hard_max: ratio
    """
    points = load_model_points(config)  # モデルポイント一覧を読む
    ratios = _iter_range(start, end, step)  # rの範囲を作る

    rows: list[dict[str, float | int | str]] = []  # 結果行を初期化する
    min_r_by_id: dict[str, float | None] = {  # 最小r辞書を初期化する
        point.model_point_id: None for point in points
    }  # 最小r辞書

    for ratio in ratios:  # rをスイープする
        for point in points:  # 各モデルポイントを計算する
            gross_annual_premium = int(  # 総保険料を計算する
                round(ratio * point.sum_assured / point.premium_paying_years, 0)
            )  # 総保険料の算出
            metrics = _calc_sweep_metrics(  # 指標を計算する
                config=config,  # 設定
                base_dir=base_dir,  # 相対パス基準
                model_point=point,  # モデルポイント
                gross_annual_premium=gross_annual_premium,  # 総保険料
            )  # 指標結果
            if min_r_by_id[point.model_point_id] is None:  # 最小rが未設定の場合
                if (  # 複数条件を満たしたら最小rを設定する
                    metrics["irr"] >= irr_threshold
                    and metrics["nbv"] >= nbv_threshold
                    and metrics["loading_surplus_ratio"]
                    >= loading_surplus_ratio_threshold
                    and metrics["premium_to_maturity"] <= premium_to_maturity_hard_max
                ):  # 条件判定
                    min_r_by_id[point.model_point_id] = ratio  # 最小rを記録する

            rows.append(  # 行データを追加する
                {
                    "model_point_id": point.model_point_id,  # モデルポイントID
                    "sex": point.sex,  # 性別
                    "issue_age": point.issue_age,  # 年齢
                    "term_years": point.term_years,  # 保険期間
                    "premium_paying_years": point.premium_paying_years,  # 払込期間
                    "sum_assured": point.sum_assured,  # 保険金額
                    "r": ratio,  # PTM比率
                    "gross_annual_premium": gross_annual_premium,  # 総保険料
                    "irr": metrics["irr"],  # IRR
                    "nbv": metrics["nbv"],  # NBV
                    "loading_surplus": metrics["loading_surplus"],  # 充足額
                    "loading_surplus_ratio": metrics["loading_surplus_ratio"],  # 充足比率
                    "premium_to_maturity": metrics["premium_to_maturity"],  # PTM比率
                }
            )  # 行追加

    df = pd.DataFrame(rows)  # DataFrameに変換する
    out_path.parent.mkdir(parents=True, exist_ok=True)  # 出力先ディレクトリを作る
    df.to_csv(out_path, index=False)  # CSVとして保存する
    return df, min_r_by_id  # 結果と最小r辞書を返す
