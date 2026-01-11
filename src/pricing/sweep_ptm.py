from __future__ import annotations  # 型注釈の前方参照を許可し、循環参照を避けるため

"""
Sweep premium-to-maturity ratios and evaluate IRR for a model point.
"""

from dataclasses import dataclass  # モデルポイント情報を構造化するため
from pathlib import Path  # パスをOS非依存で扱うため
from typing import Iterable, Mapping  # 型注釈で入出力を明確にするため

import pandas as pd  # 結果テーブルを扱うため

from .commutation import build_mortality_q_by_age  # 死亡率辞書の構築に使うため
from .endowment import calc_endowment_premiums  # 保険料計算に使うため
from .profit_test import (  # 収益性検証の一部ロジックを再利用するため
    DEFAULT_LAPSE_RATE,  # 失効率の既定値
    DEFAULT_VALUATION_INTEREST,  # 評価利率の既定値
    _forward_rates_from_spot,  # フォワードレート計算
    _inforce_series,  # 保有率系列計算
    _reserve_factors,  # 準備金係数計算
    _resolve_path,  # パス解決
    calc_irr,  # IRR計算
    load_mortality_csv,  # 死亡率CSV読み込み
    load_spot_curve_csv,  # スポットカーブCSV読み込み
)


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


def _calc_sweep_metrics(  # スイープ1点の指標を計算する
    config: Mapping[str, object],  # 設定
    base_dir: Path,  # 相対パス基準
    model_point: SweepModelPoint,  # モデルポイント
    gross_annual_premium: int,  # 総保険料（年額）
) -> dict[str, float]:  # 指標を辞書で返す
    pricing = config["pricing"]  # 予定利率・死亡率設定
    loadings = config["loading_alpha_beta_gamma"]  # 直接指定のalpha/beta/gamma
    profit_test_cfg = config.get("profit_test", {})  # 収益性検証設定

    interest_cfg = pricing["interest"]  # 予定利率設定
    if interest_cfg.get("type") != "flat":  # フラット利率以外は未対応
        raise ValueError("Only flat interest rate is supported.")  # 未対応を通知する
    pricing_interest = float(interest_cfg["flat_rate"])  # 予定利率を取得する
    valuation_interest = float(  # 評価利率を取得する
        profit_test_cfg.get("valuation_interest_rate", DEFAULT_VALUATION_INTEREST)
    )  # 既定値で補完する
    lapse_rate = float(profit_test_cfg.get("lapse_rate", DEFAULT_LAPSE_RATE))  # 失効率を取得する

    alpha = float(loadings["alpha"])  # alphaを取得する
    beta = float(loadings["beta"])  # betaを取得する
    gamma = float(loadings["gamma"])  # gammaを取得する

    pricing_mortality_path = _resolve_path(base_dir, pricing["mortality_path"])  # 予定死亡率パスを解決する
    actual_mortality_path = _resolve_path(  # 実績死亡率パスを解決する
        base_dir, profit_test_cfg["mortality_actual_path"]
    )  # 実績死亡率パスの解決
    spot_curve_path = _resolve_path(base_dir, profit_test_cfg["discount_curve_path"])  # スポットカーブパスを解決する

    pricing_rows = load_mortality_csv(pricing_mortality_path)  # 予定死亡率CSVを読み込む
    actual_rows = load_mortality_csv(actual_mortality_path)  # 実績死亡率CSVを読み込む
    spot_curve = load_spot_curve_csv(spot_curve_path)  # スポットカーブCSVを読み込む
    forward_rates = _forward_rates_from_spot(spot_curve, model_point.term_years)  # フォワードレートを作る

    premiums = calc_endowment_premiums(  # 保険料を計算する
        mortality_rows=pricing_rows,  # 予定死亡率
        sex=model_point.sex,  # 性別
        issue_age=model_point.issue_age,  # 年齢
        term_years=model_point.term_years,  # 保険期間
        premium_paying_years=model_point.premium_paying_years,  # 払込期間
        interest_rate=pricing_interest,  # 予定利率
        sum_assured=model_point.sum_assured,  # 保険金額
        alpha=alpha,  # alpha
        beta=beta,  # beta
        gamma=gamma,  # gamma
    )  # 保険料計算結果

    q_pricing = build_mortality_q_by_age(pricing_rows, model_point.sex)  # 予定死亡率の辞書
    q_actual = build_mortality_q_by_age(actual_rows, model_point.sex)  # 実績死亡率の辞書

    tV_pricing, tW_pricing, _ = _reserve_factors(  # 予定準備金係数
        q_by_age=q_pricing,  # 予定死亡率
        issue_age=model_point.issue_age,  # 年齢
        term_years=model_point.term_years,  # 期間
        premium_paying_years=model_point.premium_paying_years,  # 払込期間
        interest_rate=pricing_interest,  # 予定利率
        alpha=alpha,  # alpha
    )  # 予定準備金係数
    tV_valuation, _, _ = _reserve_factors(  # 評価準備金係数
        q_by_age=q_pricing,  # 予定死亡率
        issue_age=model_point.issue_age,  # 年齢
        term_years=model_point.term_years,  # 期間
        premium_paying_years=model_point.premium_paying_years,  # 払込期間
        interest_rate=valuation_interest,  # 評価利率
        alpha=alpha,  # alpha
    )  # 評価準備金係数

    inforce_begin, inforce_end, death_rates, lapse_rates = _inforce_series(  # 保有率系列
        q_by_age=q_actual,  # 実績死亡率
        issue_age=model_point.issue_age,  # 年齢
        term_years=model_point.term_years,  # 期間
        lapse_rate=lapse_rate,  # 失効率
    )  # 保有率系列

    net_cfs: list[float] = []  # 純キャッシュフロー系列
    pv_net_cf = 0.0  # NBVの計算用
    pv_loading = 0.0  # loading現価
    pv_expense = 0.0  # 費用現価

    for t in range(model_point.term_years):  # 各年を計算する
        if t + 1 not in spot_curve:  # スポットレートが欠損している場合
            raise ValueError(f"Missing spot rate for t={t + 1}.")  # 欠損を通知する
        spot_rate = spot_curve[t + 1]  # スポットレートを取得する
        forward_rate = forward_rates[t]  # フォワードレートを取得する

        inforce_beg = inforce_begin[t]  # 期首保有率
        inforce_end_t = inforce_end[t]  # 期末保有率
        q_t = death_rates[t]  # 死亡率
        w_t = lapse_rates[t]  # 失効率

        is_premium_year = t < model_point.premium_paying_years  # 当年が払込期間かを判定する

        premium_income = (  # 保険料収入
            gross_annual_premium * inforce_beg if is_premium_year else 0.0
        )  # 払込期間のみ計上する
        net_premium_income = (  # 純保険料収入
            premiums.net_annual_premium * inforce_beg if is_premium_year else 0.0
        )  # 払込期間のみ計上する
        loading_income = premium_income - net_premium_income  # loading収入を計算する

        death_benefit = (  # 死亡給付
            inforce_beg * q_t * model_point.sum_assured if is_premium_year else 0.0
        )  # 払込期間のみ計上する
        surrender_benefit = (  # 解約返戻金
            inforce_beg
            * w_t
            * (tW_pricing[t] + tW_pricing[t + 1])
            / 2.0
            * model_point.sum_assured
            if is_premium_year
            else 0.0
        )  # 解約返戻金を計算する
        maturity_benefit = (  # 満期給付
            inforce_end_t * model_point.sum_assured
            if t == model_point.term_years - 1
            else 0.0
        )  # 満期年のみ計上する

        expenses_acq = (0.5 * alpha * model_point.sum_assured) if t == 0 else 0.0  # 獲得費を計上する
        expenses_maint = (  # 維持費を計上する
            inforce_beg * model_point.sum_assured * beta if is_premium_year else 0.0
        )  # 払込期間のみ計上する
        expenses_coll = (  # 集金費を計上する
            inforce_beg * gross_annual_premium * gamma if is_premium_year else 0.0
        )  # 払込期間のみ計上する
        expenses_total = expenses_acq + expenses_maint + expenses_coll  # 総費用を合算する

        reserve_change = (  # 準備金増減
            model_point.sum_assured
            * (inforce_end_t * tV_valuation[t + 1] - inforce_beg * tV_valuation[t])
            if is_premium_year
            else 0.0
        )  # 払込期間のみ計上する

        investment_income = (  # 運用収益
            (
                inforce_beg * tV_valuation[t] * model_point.sum_assured
                + premium_income
                - expenses_total
            )
            * forward_rate
            - (death_benefit + surrender_benefit) * ((1.0 + forward_rate) ** 0.5 - 1.0)
            if is_premium_year
            else 0.0
        )  # 払込期間のみ計上する

        net_cf = (  # 純キャッシュフロー
            premium_income
            + investment_income
            - (death_benefit + surrender_benefit + expenses_total + reserve_change)
        )  # 収支を計算する
        net_cfs.append(net_cf)  # 純キャッシュフローを追加する

        spot_df = (1.0 / (1.0 + spot_rate)) ** (t + 1)  # 割引係数を計算する
        pv_net_cf += net_cf * spot_df  # NBVを加算する
        pv_loading += loading_income * spot_df  # loading現価を加算する
        pv_expense += expenses_total * spot_df  # 費用現価を加算する

    irr = calc_irr(net_cfs)  # IRRを計算する
    loading_surplus = pv_loading - pv_expense  # 充足額を計算する

    premium_to_maturity = (  # PTM比率を計算する
        gross_annual_premium * model_point.premium_paying_years / model_point.sum_assured
    )  # PTM比率

    return {  # 指標を辞書で返す
        "irr": irr,  # IRR
        "nbv": pv_net_cf,  # NBV
        "loading_surplus": loading_surplus,  # 充足額
        "loading_surplus_ratio": loading_surplus / model_point.sum_assured,  # 充足比率
        "premium_to_maturity": premium_to_maturity,  # PTM比率
    }  # 指標の返却


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
