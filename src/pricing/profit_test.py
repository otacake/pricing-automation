from __future__ import annotations  # 型注釈の前方参照を許可し、循環参照を避けるため

"""
Profit test for a traditional endowment product.

Cashflow columns are aligned with the Excel sheet "収益性検証":
- net_cf corresponds to column C (収支)
- spot_df corresponds to column S (スポット現価)
- new_business_value corresponds to Excel C3 (sum of net_cf * spot_df)
- irr corresponds to Excel B1 (IRR of net_cf series)
"""

from dataclasses import dataclass  # 計算結果の構造を明確にするため
from pathlib import Path  # ファイルパスをOS非依存で扱うため
from typing import Iterable, Mapping  # 型注釈で入出力を明確にするため
import pandas as pd  # テーブル計算に使うため

from .commutation import build_mortality_q_by_age, survival_probabilities  # 死亡率と生存確率の計算に使うため
from .config import read_loading_parameters  # loading係数の読み込みに使うため
from .endowment import (  # 保険料計算に必要な型と関数を取り込むため
    EndowmentPremiums,  # 保険料計算結果の型
    LoadingFunctionParams,  # loading係数の型
    LoadingParameters,  # loading計算結果の型
    calc_endowment_premiums,  # 養老保険の保険料計算
    calc_loading_parameters,  # loading係数からalpha/beta/gammaを算出
)

DEFAULT_VALUATION_INTEREST = 0.0025  # 評価利率の既定値
DEFAULT_LAPSE_RATE = 0.03  # 失効率の既定値


@dataclass(frozen=True)  # モデルポイントを不変に扱い、計算途中の事故変更を防ぐ
class ModelPoint:  # モデルポイントの入力条件をまとめる
    """
    Model point definition.

    Units
    - model_point_id: identifier for logs/config selection
    - issue_age: years
    - term_years / premium_paying_years: years
    - sum_assured: JPY
    - sex: "male" / "female"
    """

    model_point_id: str | None  # モデルポイントのID（ログや設定の識別用）
    issue_age: int  # 加入年齢
    sex: str  # 性別
    term_years: int  # 保険期間
    premium_paying_years: int  # 払込期間
    sum_assured: int  # 保険金額


@dataclass(frozen=True)  # 会社費用前提を安全に保持するため
class ExpenseAssumptions:  # 会社費用の年次前提をまとめる
    """
    Expense assumptions estimated from company data.

    Units
    - year: calendar year
    - acq_per_policy: JPY per policy
    - maint_per_policy: JPY per policy-year
    - coll_rate: ratio per premium income
    """

    year: int  # 対象年
    acq_per_policy: float  # 獲得費単価
    maint_per_policy: float  # 維持費単価
    coll_rate: float  # 集金費率


@dataclass(frozen=True)  # 1モデルポイントの結果をまとめるため
class ProfitTestResult:  # 収益性検証の結果を保持する
    """
    Profit test outputs for one model point.

    Units
    - cashflow: annual cashflow table (JPY)
    - irr: internal rate of return (annual rate)
    - new_business_value: sum of discounted net cashflows (JPY)
    - premiums: endowment premiums and factors
    - pv_loading: discounted loading income (JPY)
    - pv_expense: discounted expense outflows (JPY)
    - loading_surplus: pv_loading - pv_expense (JPY)
    - premium_total: gross annual premium * premium years (JPY)
    - premium_to_maturity_ratio: premium_total / sum_assured
    """

    model_point: ModelPoint  # モデルポイント条件
    loadings: LoadingParameters  # 使用したalpha/beta/gamma
    cashflow: pd.DataFrame  # 年次キャッシュフロー表
    irr: float  # 内部収益率
    new_business_value: float  # 新契約価値
    premiums: EndowmentPremiums  # 保険料計算結果
    pv_loading: float  # loadingの現価合計
    pv_expense: float  # 費用の現価合計
    loading_surplus: float  # loading現価 - 費用現価
    premium_total: float  # 総払込保険料
    premium_to_maturity_ratio: float  # 総払込/満期保険金


@dataclass(frozen=True)  # 複数モデルポイント結果を不変で扱うため
class ProfitTestBatchResult:  # バッチ結果をまとめる
    """
    Profit test outputs for multiple model points.

    Units
    - summary: model-point summary table (JPY, rates)
    - expense_assumptions: company expense assumptions (if used)
    """

    results: list[ProfitTestResult]  # 各モデルポイントの結果
    summary: pd.DataFrame  # サマリ表
    expense_assumptions: ExpenseAssumptions | None  # 会社費用前提（利用時のみ）


def _resolve_path(base_dir: Path, path_str: str) -> Path:  # 相対パスを基準ディレクトリに解決する
    path = Path(path_str)  # 文字列をPathに変換する
    return path if path.is_absolute() else base_dir / path  # 絶対パスならそのまま、相対なら基準を付ける


def load_company_expense_assumptions(  # 会社費用CSVから単価等を推定する
    path: Path,  # CSVパス
    year: int | None,  # 対象年（未指定なら先頭行）
    overhead_split_acq: float,  # 共通費の獲得配賦比率
    overhead_split_maint: float,  # 共通費の維持配賦比率
) -> ExpenseAssumptions:  # 推定した費用前提を返す
    """
    Estimate expense assumptions from company expense CSV.

    Units
    - acq_per_policy / maint_per_policy: JPY
    - coll_rate: ratio per premium income
    """
    if not path.is_file():  # ファイルが存在しない場合
        raise ValueError(f"Company expense file not found: {path}")  # 早期にエラーを出す
    df = pd.read_csv(path)  # CSVを読み込む
    if df.empty:  # 空ファイルなら計算できない
        raise ValueError(f"Company expense file is empty: {path}")  # エラーで通知する

    if year is None:  # 年指定が無い場合は先頭行を使う
        row = df.iloc[0]  # 先頭行を取得する
    else:  # 年指定がある場合
        matched = df[df["year"] == year]  # 指定年に一致する行を抽出する
        if matched.empty:  # 該当年が無ければエラー
            raise ValueError(f"Company expense year not found: {year}")  # エラーで通知する
        row = matched.iloc[0]  # 対象年の行を取得する

    new_policies = float(row["new_policies"])  # 新契約件数を取得する
    inforce_avg = float(row["inforce_avg"])  # 平均保有件数を取得する
    premium_income = float(row["premium_income"])  # 保険料収入を取得する
    if new_policies <= 0 or inforce_avg <= 0 or premium_income <= 0:  # 分母が0以下は不正
        raise ValueError("Company expense denominators must be positive.")  # 早期にエラーを出す

    acq_per_policy = (  # 獲得費単価を推定する
        float(row["acq_var_total"])  # 獲得変動費
        + float(row["acq_fixed_total"])  # 獲得固定費
        + float(row["overhead_total"]) * float(overhead_split_acq)  # 共通費の獲得配賦分
    ) / new_policies  # 件数で割って単価化する
    maint_per_policy = (  # 維持費単価を推定する
        float(row["maint_var_total"])  # 維持変動費
        + float(row["maint_fixed_total"])  # 維持固定費
        + float(row["overhead_total"]) * float(overhead_split_maint)  # 共通費の維持配賦分
    ) / inforce_avg  # 保有件数で割って単価化する
    coll_rate = float(row["coll_var_total"]) / premium_income  # 集金費率を計算する

    if acq_per_policy < 0 or maint_per_policy < 0 or coll_rate < 0:  # 予定事業費は負値不可
        raise ValueError("Company expense assumptions must be non-negative.")

    return ExpenseAssumptions(  # 推定結果をデータクラスにまとめて返す
        year=int(row["year"]),  # 年
        acq_per_policy=acq_per_policy,  # 獲得費単価
        maint_per_policy=maint_per_policy,  # 維持費単価
        coll_rate=coll_rate,  # 集金費率
    )  # 結果を返す


def model_point_label(model_point: ModelPoint) -> str:  # モデルポイントの表示用ラベルを作る
    """
    Build a compact label for logs and tables.
    """
    if model_point.model_point_id:  # IDが指定されていればそれを使う
        return model_point.model_point_id  # IDを返す
    return (  # IDが無ければ性別・年齢・期間の組み合わせで作る
        f"{model_point.sex}_age{model_point.issue_age}"  # 性別と年齢を入れる
        f"_term{model_point.term_years}"  # 期間を入れる
    )  # ラベルを返す


def load_mortality_csv(path: Path) -> list[dict[str, float | int | None]]:  # 死亡率CSVを読み込む
    """
    Load mortality CSV into a list of dicts with keys: age, q_male, q_female.
    """
    df = pd.read_csv(path)  # CSVを読み込む
    return df.to_dict(orient="records")  # 行ごとの辞書リストに変換して返す


def load_spot_curve_csv(path: Path) -> dict[int, float]:  # スポットカーブCSVを読み込む
    """
    Load spot curve CSV into a dict of {t: spot_rate}.
    """
    df = pd.read_csv(path)  # CSVを読み込む
    result: dict[int, float] = {}  # 結果辞書を初期化する
    for _, row in df.iterrows():  # 各行を走査する
        t = int(row["t"])  # 期間を整数で取得する
        result[t] = float(row["spot_rate"])  # スポットレートを登録する
    return result  # 期間→スポットレートの辞書を返す


def _forward_rates_from_spot(spot_curve: Mapping[int, float], term_years: int) -> list[float]:  # スポットからフォワードを作る
    """
    Compute one-year forward rates from spot rates.

    forward_t = (1+spot_{t+1})^(t+1) / (1+spot_t)^t - 1
    """
    forward_rates: list[float] = []  # 結果リストを初期化する
    for t in range(term_years):  # 期間分のフォワードを計算する
        spot_next = spot_curve[t + 1]  # t+1年のスポットを取得する
        if t == 0:  # 初年度はそのまま使用する
            forward_rates.append(spot_next)  # 1年目のフォワードとして追加する
            continue  # 次の年へ進む
        spot_prev = spot_curve[t]  # t年のスポットを取得する
        forward = ((1.0 + spot_next) ** (t + 1) / (1.0 + spot_prev) ** t) - 1.0  # フォワードを計算する
        forward_rates.append(forward)  # 計算値を追加する
    return forward_rates  # フォワードレートのリストを返す


def _calc_endowment_values(  # Aとaの計算に必要な中間値を求める
    q_by_age: Mapping[int, float],  # 年齢別死亡率
    issue_age: int,  # 加入年齢
    term_years: int,  # 保険期間
    premium_paying_years: int,  # 払込期間
    interest_rate: float,  # 予定利率
) -> tuple[float, float]:  # Aとaを返す
    """
    Calculate A and a for the given term and premium horizon.

    - A_death = sum v^(t+0.5) * p_{x:t} * q_{x+t}
    - A_maturity = v^n * p_{x:n}
    - a = sum v^t * p_{x:t}
    """
    if term_years < 0 or premium_paying_years < 0:  # 期間が負なら不正
        raise ValueError("term_years and premium_paying_years must be non-negative.")  # エラーで通知する
    if term_years == 0:  # 期間0なら給付係数の定義を簡略化する
        return 1.0, 0.0  # A=1, a=0として返す

    p = survival_probabilities(q_by_age, issue_age, term_years)  # 生存確率系列を作る
    v = 1.0 / (1.0 + interest_rate)  # 割引係数を計算する

    death_pv = 0.0  # 死亡給付の現価を初期化する
    for t in range(term_years):  # 各年の死亡給付を積算する
        age = issue_age + t  # 対象年齢を求める
        death_pv += (v ** (t + 0.5)) * p[t] * q_by_age[age]  # 中間死亡の現価を加算する

    maturity_pv = (v ** term_years) * p[term_years]  # 満期給付の現価を計算する
    A = death_pv + maturity_pv  # 死亡と満期を合算した係数

    annuity = 0.0  # 年金現価係数を初期化する
    for t in range(premium_paying_years):  # 払込期間分を積算する
        annuity += (v ** t) * p[t]  # 年金現価を加算する

    return A, annuity  # Aとaを返す


def _reserve_factors(  # 予定・評価の準備金係数を計算する
    q_by_age: Mapping[int, float],  # 年齢別死亡率
    issue_age: int,  # 加入年齢
    term_years: int,  # 保険期間
    premium_paying_years: int,  # 払込期間
    interest_rate: float,  # 利率
    alpha: float,  # loadingのalpha
) -> tuple[list[float], list[float], float]:  # tV, tW, net_rateを返す
    """
    Build tV and tW series for t=0..term_years.

    - tV = A(x+t:n-t) - net_rate * a(x+t:n-t)
    - tW = max(tV - ((10 - min(t,10)) / 10) * alpha, 0)
    """
    A0, a0 = _calc_endowment_values(  # 初期時点のAとaを計算する
        q_by_age=q_by_age,  # 年齢別死亡率
        issue_age=issue_age,  # 加入年齢
        term_years=term_years,  # 保険期間
        premium_paying_years=premium_paying_years,  # 払込期間
        interest_rate=interest_rate,  # 利率
    )  # Aとaの計算
    if a0 <= 0.0:  # 年金現価が非正なら計算不能
        raise ValueError("Premium annuity factor must be positive.")  # エラーを出す
    net_rate = A0 / a0  # 純保険料率を求める

    tV: list[float] = []  # tV系列を初期化する
    tW: list[float] = []  # tW系列を初期化する
    for t in range(term_years + 1):  # t=0..nまで計算する
        remaining_term = term_years - t  # 残存期間を求める
        remaining_premium = max(premium_paying_years - t, 0)  # 残存払込期間を求める
        A_t, a_t = _calc_endowment_values(  # 各時点のAとaを計算する
            q_by_age=q_by_age,  # 年齢別死亡率
            issue_age=issue_age + t,  # 時点tの年齢
            term_years=remaining_term,  # 残存期間
            premium_paying_years=remaining_premium,  # 残存払込期間
            interest_rate=interest_rate,  # 利率
        )  # Aとaの計算
        reserve = A_t - net_rate * a_t  # 予定準備金係数を計算する
        tV.append(reserve)  # tVに追加する
        surrender_adj = (10 - min(t, 10)) / 10.0  # 10年逓減の解約控除係数
        tW.append(max(reserve - surrender_adj * alpha, 0.0))  # 解約返戻金係数を計算する

    return tV, tW, net_rate  # tV, tW, 純保険料率を返す


def _inforce_series(  # 保有件数の推移と退出率を計算する
    q_by_age: Mapping[int, float],  # 年齢別死亡率
    issue_age: int,  # 加入年齢
    term_years: int,  # 保険期間
    lapse_rate: float,  # 失効率
) -> tuple[list[float], list[float], list[float], list[float]]:  # inforceと死亡/失効率を返す
    """
    Build inforce and exit-rate series using the Excel definitions.

    - death_rate = q * (1 - lapse / 2)
    - lapse_rate = lapse * (1 - q / 2)
    - inforce_end = inforce_begin * (1 - death_rate - lapse_rate)
    """
    inforce_begin = [1.0]  # 期首保有率の初期値
    inforce_end: list[float] = []  # 期末保有率を初期化する
    death_rates: list[float] = []  # 死亡率系列を初期化する
    lapse_rates: list[float] = []  # 失効率系列を初期化する

    for t in range(term_years):  # 期間分の推移を計算する
        age = issue_age + t  # t年後の年齢を求める
        if age not in q_by_age:  # 死亡率が欠損なら計算できない
            raise ValueError(f"Missing mortality rate for age {age}.")  # 欠損を通知する
        q = q_by_age[age]  # 年齢の死亡率を取得する
        death_rate = q * (1.0 - lapse_rate / 2.0)  # Excel定義に合わせた死亡率を計算する
        lapse_adj = lapse_rate * (1.0 - q / 2.0)  # Excel定義に合わせた失効率を計算する
        inforce_next = inforce_begin[-1] * (1.0 - death_rate - lapse_adj)  # 期末保有率を計算する

        death_rates.append(death_rate)  # 死亡率を追加する
        lapse_rates.append(lapse_adj)  # 失効率を追加する
        inforce_end.append(inforce_next)  # 期末保有率を追加する
        inforce_begin.append(inforce_next)  # 次期の期首として追加する

    return inforce_begin[:-1], inforce_end, death_rates, lapse_rates  # 系列を返す


def calc_irr(  # 年次キャッシュフローからIRRを計算する
    cashflows: Iterable[float],  # キャッシュフロー系列
    tol: float = 1e-12,  # NPVの許容誤差
    rate_tol: float = 1e-12,  # 金利の許容誤差
    max_iter: int = 200,  # 最大反復回数
) -> float:  # IRRを返す
    """
    Compute IRR for annual cashflows using bisection.
    """
    flows = list(cashflows)  # 反復計算のためにリスト化する
    if not flows:  # 空のキャッシュフローは無効
        raise ValueError("Cashflows must be non-empty.")  # エラーで通知する

    def npv(rate: float) -> float:  # NPVを計算する内関数
        return sum(cf / ((1.0 + rate) ** t) for t, cf in enumerate(flows))  # 各期の割引現在価値を合計する

    low = -0.999999  # 下限（-100%に近い値）
    high = 1.0  # 上限（初期値）
    f_low = npv(low)  # 下限でのNPV
    f_high = npv(high)  # 上限でのNPV
    while f_low * f_high > 0 and high < 1024:  # 符号が同じなら範囲を広げる
        high *= 2.0  # 上限を倍々に広げる
        f_high = npv(high)  # 新しい上限でNPVを計算する

    if f_low * f_high > 0:  # 符号が変わらなければ根がない
        raise ValueError("IRR not bracketed.")  # IRRが見つからないと判断する

    for _ in range(max_iter):  # 二分法でIRRを探索する
        mid = (low + high) / 2.0  # 中点を取る
        f_mid = npv(mid)  # 中点でNPVを計算する
        if abs(f_mid) < tol:  # 目標誤差内なら収束
            return mid  # IRRとして返す
        if f_low * f_mid <= 0:  # 根が下側にある場合
            high = mid  # 上限を中点に更新する
            f_high = f_mid  # 上限のNPVも更新する
        else:  # 根が上側にある場合
            low = mid  # 下限を中点に更新する
            f_low = f_mid  # 下限のNPVも更新する
        if high - low < rate_tol:  # 金利の幅が許容範囲なら終了
            return (high + low) / 2.0  # 中点をIRRとして返す

    raise ValueError("IRR did not converge.")  # 反復回数内に収束しなければエラー


def _parse_model_points(config: Mapping[str, object]) -> list[ModelPoint]:  # YAMLからモデルポイントを読み込む
    product = config.get("product", {}) if isinstance(config, Mapping) else {}  # 商品設定を取得する
    defaults = {  # 商品設定からデフォルト値を作る
        "term_years": product.get("term_years"),  # 保険期間のデフォルト
        "premium_paying_years": product.get("premium_paying_years"),  # 払込期間のデフォルト
        "sum_assured": product.get("sum_assured"),  # 保険金額のデフォルト
    }  # デフォルト値の辞書

    points_cfg = config.get("model_points") if isinstance(config, Mapping) else None  # 複数モデルポイントを取得する
    if points_cfg is None:  # 複数定義がなければ単独定義を使う
        points_cfg = [config.get("model_point")] if isinstance(config, Mapping) else []  # 単独定義をリスト化する

    if not points_cfg:  # 定義が無ければエラー
        raise ValueError("Model points are missing.")  # エラーで通知する

    points: list[ModelPoint] = []  # 結果のリストを初期化する
    for entry in points_cfg:  # 各モデルポイント設定を処理する
        if not isinstance(entry, Mapping):  # dictでなければスキップする
            continue  # 次へ進む
        issue_age = int(entry["issue_age"])  # 年齢を取得する
        sex = str(entry["sex"])  # 性別を取得する
        term_years = int(entry.get("term_years", defaults["term_years"]))  # 保険期間を取得する
        premium_paying_years = int(  # 払込期間を取得する
            entry.get("premium_paying_years", defaults["premium_paying_years"])
        )  # 払込期間の取得
        sum_assured = int(entry.get("sum_assured", defaults["sum_assured"]))  # 保険金額を取得する
        model_point_id = entry.get("id")  # モデルポイントIDを取得する
        points.append(  # モデルポイントを追加する
            ModelPoint(  # ModelPointを構築する
                model_point_id=str(model_point_id) if model_point_id is not None else None,  # IDがあれば文字列化
                issue_age=issue_age,  # 年齢
                sex=sex,  # 性別
                term_years=term_years,  # 保険期間
                premium_paying_years=premium_paying_years,  # 払込期間
                sum_assured=sum_assured,  # 保険金額
            )  # モデルポイント構築
        )  # リストに追加

    if not points:  # 有効なモデルポイントが無い場合
        raise ValueError("Model points are missing.")  # エラーを通知する
    return points  # モデルポイント一覧を返す


def _resolve_loading_parameters(  # loading係数を確定させる
    config: Mapping[str, object],  # 設定
    model_point: ModelPoint,  # モデルポイント
    loading_params: LoadingFunctionParams | None,  # 外部から渡された係数
) -> LoadingParameters:  # alpha/beta/gammaを返す
    if loading_params is not None:  # 呼び出し側が係数を指定している場合
        return calc_loading_parameters(  # 係数からalpha/beta/gammaを算出する
            loading_params,  # 係数
            issue_age=model_point.issue_age,  # 年齢
            term_years=model_point.term_years,  # 保険期間
            sex=model_point.sex,  # 性別
        )  # 計算結果を返す

    params = read_loading_parameters(config) if isinstance(config, Mapping) else None  # 設定から係数を読む
    if params is not None:  # 係数が取得できた場合
        return calc_loading_parameters(  # 係数からalpha/beta/gammaを算出する
            params,  # 係数
            issue_age=model_point.issue_age,  # 年齢
            term_years=model_point.term_years,  # 保険期間
            sex=model_point.sex,  # 性別
        )  # 計算結果を返す

    loadings_cfg = config.get("loading_alpha_beta_gamma", {}) if isinstance(config, Mapping) else {}  # 旧形式の直接指定を読む
    if not isinstance(loadings_cfg, Mapping):  # 形式が不正ならエラー
        raise ValueError("loading_alpha_beta_gamma must be a mapping.")  # 入力の誤りを通知する
    return LoadingParameters(  # 直接指定のalpha/beta/gammaを使う
        alpha=float(loadings_cfg["alpha"]),  # alpha
        beta=float(loadings_cfg["beta"]),  # beta
        gamma=float(loadings_cfg["gamma"]),  # gamma
    )  # 計算結果を返す


def _load_expense_assumptions(  # 費用モデルの設定を読み込む
    config: Mapping[str, object],  # 設定
    base_dir: Path,  # 相対パスの基準
) -> tuple[str, ExpenseAssumptions | None]:  # 費用モデルのモードと前提を返す
    profit_test_cfg = config.get("profit_test", {}) if isinstance(config, Mapping) else {}  # 収益性検証設定を取得する
    expense_cfg = profit_test_cfg.get("expense_model", {}) if isinstance(profit_test_cfg, Mapping) else {}  # 費用モデル設定を取得する
    mode = str(expense_cfg.get("mode", "company"))  # モードを取得する（既定はcompany）

    if mode == "loading":  # loadingモードの場合は会社費用を使わない
        return mode, None  # モードとNoneを返す
    if mode != "company":  # company以外は未対応
        raise ValueError(f"Unsupported expense model mode: {mode}")  # エラーを出す

    if "company_data_path" not in expense_cfg:  # companyモードではCSVパスが必須
        raise ValueError("company_data_path is required for company expense model.")  # エラーを出す

    overhead_cfg = expense_cfg.get("overhead_split", {}) if isinstance(expense_cfg, Mapping) else {}  # 共通費配賦設定
    if not overhead_cfg:  # 旧キー互換
        overhead_cfg = expense_cfg.get("include_overhead_as", {}) if isinstance(expense_cfg, Mapping) else {}
    overhead_split_acq = float(overhead_cfg.get("acquisition", 0.0))  # 獲得配賦比率
    overhead_split_maint = float(overhead_cfg.get("maintenance", 0.0))  # 維持配賦比率
    year = expense_cfg.get("year")  # 年度指定を取得する
    year_value = int(year) if year is not None else None  # 年度指定をint化する

    expense_path = _resolve_path(base_dir, str(expense_cfg["company_data_path"]))  # パスを基準ディレクトリに解決する
    assumptions = load_company_expense_assumptions(  # CSVから費用前提を推定する
        expense_path,  # CSVパス
        year=year_value,  # 対象年度
        overhead_split_acq=overhead_split_acq,  # 獲得配賦比率
        overhead_split_maint=overhead_split_maint,  # 維持配賦比率
    )  # 前提の推定結果
    return mode, assumptions  # モードと前提を返す


def _build_summary(results: list[ProfitTestResult]) -> pd.DataFrame:  # モデルポイント結果のサマリ表を作る
    rows: list[dict[str, float | int | str]] = []  # 行のリストを初期化する
    for result in results:  # 各モデルポイントの結果を処理する
        point = result.model_point  # モデルポイントを取り出す
        rows.append(  # サマリ行を追加する
            {
                "model_point": model_point_label(point),  # ラベル
                "sex": point.sex,  # 性別
                "issue_age": point.issue_age,  # 年齢
                "term_years": point.term_years,  # 保険期間
                "premium_paying_years": point.premium_paying_years,  # 払込期間
                "sum_assured": point.sum_assured,  # 保険金額
                "net_annual_premium": result.premiums.net_annual_premium,  # 年払純保険料
                "gross_annual_premium": result.premiums.gross_annual_premium,  # 年払総保険料
                "monthly_premium": result.premiums.monthly_premium,  # 月払保険料
                "irr": result.irr,  # IRR
                "new_business_value": result.new_business_value,  # NBV
                "pv_loading": result.pv_loading,  # loading現価
                "pv_expense": result.pv_expense,  # 費用現価
                "loading_surplus": result.loading_surplus,  # 充足額
                "premium_total": result.premium_total,  # 総払込
                "premium_to_maturity_ratio": result.premium_to_maturity_ratio,  # PTM比率
            }
        )  # 行追加
    return pd.DataFrame(rows)  # DataFrameに変換して返す


def run_profit_test(  # profit testを実行するメイン関数
    config: dict,  # 設定
    base_dir: Path | None = None,  # 相対パス基準
    loading_params: LoadingFunctionParams | None = None,  # 任意の係数上書き
) -> ProfitTestBatchResult:  # バッチ結果を返す
    """
    Run profit test using the YAML config structure.

    Units
    - base_dir: root for relative file paths
    - loading_params: overrides loading function coefficients (not a premium scaling factor)
    """
    base_dir = base_dir or Path.cwd()  # 基準ディレクトリを決定する

    product = config["product"]  # 商品設定を取得する
    pricing = config["pricing"]  # 予定利率と死亡率設定を取得する
    profit_test_cfg = config.get("profit_test", {})  # 収益性検証の設定を取得する

    model_points = _parse_model_points(config)  # モデルポイントを読み込む

    interest_cfg = pricing["interest"]  # 予定利率設定を取得する
    if interest_cfg.get("type") != "flat":  # 現状はフラット利率のみ対応
        raise ValueError("Only flat interest rate is supported.")  # 未対応を明示する
    pricing_interest = float(interest_cfg["flat_rate"])  # 予定利率を取得する
    valuation_interest = float(  # 評価利率を取得する
        profit_test_cfg.get("valuation_interest_rate", DEFAULT_VALUATION_INTEREST)
    )  # 既定値で補完する
    lapse_rate = float(profit_test_cfg.get("lapse_rate", DEFAULT_LAPSE_RATE))  # 失効率を取得する

    pricing_mortality_path = _resolve_path(base_dir, pricing["mortality_path"])  # 予定死亡率パスを解決する
    actual_mortality_path = _resolve_path(  # 実績死亡率パスを解決する
        base_dir, profit_test_cfg["mortality_actual_path"]
    )  # 実績死亡率パスの解決
    spot_curve_path = _resolve_path(base_dir, profit_test_cfg["discount_curve_path"])  # スポットカーブパスを解決する

    expense_mode, expense_assumptions = _load_expense_assumptions(config, base_dir)  # 費用モデル設定を取得する

    pricing_rows = load_mortality_csv(pricing_mortality_path)  # 予定死亡率CSVを読み込む
    actual_rows = load_mortality_csv(actual_mortality_path)  # 実績死亡率CSVを読み込む
    spot_curve = load_spot_curve_csv(spot_curve_path)  # スポットカーブCSVを読み込む
    results: list[ProfitTestResult] = []  # 結果のリストを初期化する

    for model_point in model_points:  # 各モデルポイントを計算する
        loadings = _resolve_loading_parameters(config, model_point, loading_params)  # alpha/beta/gammaを確定する
        forward_rates = _forward_rates_from_spot(spot_curve, model_point.term_years)  # フォワードレートを作る

        premiums = calc_endowment_premiums(  # 保険料を計算する
            mortality_rows=pricing_rows,  # 予定死亡率
            sex=model_point.sex,  # 性別
            issue_age=model_point.issue_age,  # 年齢
            term_years=model_point.term_years,  # 保険期間
            premium_paying_years=model_point.premium_paying_years,  # 払込期間
            interest_rate=pricing_interest,  # 予定利率
            sum_assured=model_point.sum_assured,  # 保険金額
            alpha=loadings.alpha,  # alpha
            beta=loadings.beta,  # beta
            gamma=loadings.gamma,  # gamma
        )  # 保険料計算結果

        q_pricing = build_mortality_q_by_age(pricing_rows, model_point.sex)  # 予定死亡率の辞書を作る
        q_actual = build_mortality_q_by_age(actual_rows, model_point.sex)  # 実績死亡率の辞書を作る

        tV_pricing, tW_pricing, _ = _reserve_factors(  # 予定基準の準備金係数を計算する
            q_by_age=q_pricing,  # 予定死亡率
            issue_age=model_point.issue_age,  # 年齢
            term_years=model_point.term_years,  # 期間
            premium_paying_years=model_point.premium_paying_years,  # 払込期間
            interest_rate=pricing_interest,  # 予定利率
            alpha=loadings.alpha,  # alpha
        )  # 予定準備金係数
        tV_valuation, _, _ = _reserve_factors(  # 評価基準の準備金係数を計算する
            q_by_age=q_pricing,  # 予定死亡率
            issue_age=model_point.issue_age,  # 年齢
            term_years=model_point.term_years,  # 期間
            premium_paying_years=model_point.premium_paying_years,  # 払込期間
            interest_rate=valuation_interest,  # 評価利率
            alpha=loadings.alpha,  # alpha
        )  # 評価準備金係数

        inforce_begin, inforce_end, death_rates, lapse_rates = _inforce_series(  # 保有率と退出率を計算する
            q_by_age=q_actual,  # 実績死亡率
            issue_age=model_point.issue_age,  # 年齢
            term_years=model_point.term_years,  # 期間
            lapse_rate=lapse_rate,  # 失効率
        )  # 保有率系列

        records: list[dict[str, float | int]] = []  # キャッシュフロー行を初期化する
        for t in range(model_point.term_years):  # 各年のキャッシュフローを計算する
            if t + 1 not in spot_curve:  # スポットレートが欠損している場合
                raise ValueError(f"Missing spot rate for t={t + 1}.")  # 欠損を通知する
            spot_rate = spot_curve[t + 1]  # スポットレートを取得する
            forward_rate = forward_rates[t]  # フォワードレートを取得する

            inforce_beg = inforce_begin[t]  # 期首保有率
            inforce_end_t = inforce_end[t]  # 期末保有率
            q_t = death_rates[t]  # 死亡率
            w_t = lapse_rates[t]  # 失効率

            is_premium_year = t < model_point.premium_paying_years  # 当年が払込期間かを判定する

            premium_income = (  # 総保険料収入
                premiums.gross_annual_premium * inforce_beg if is_premium_year else 0.0
            )  # 払込期間のみ計上する
            net_premium_income = (  # 純保険料収入
                premiums.net_annual_premium * inforce_beg if is_premium_year else 0.0
            )  # 払込期間のみ計上する
            loading_income = premium_income - net_premium_income  # loading部分の収入を計算する

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
            if expense_mode == "company":  # 会社費用モデルの場合
                if expense_assumptions is None:  # 前提が無ければエラー
                    raise ValueError("Expense assumptions are missing.")  # 入力不備を通知する
                expenses_acq = (  # 獲得費
                    expense_assumptions.acq_per_policy * inforce_beg
                    if t == 0
                    else 0.0
                )  # 初年度のみ計上する
                expenses_maint = expense_assumptions.maint_per_policy * inforce_beg  # 維持費は毎年計上する
                expenses_coll = expense_assumptions.coll_rate * premium_income  # 集金費は保険料比例で計上する
            else:  # loadingモードの場合
                expenses_acq = (0.5 * loadings.alpha * model_point.sum_assured) if t == 0 else 0.0  # 獲得費を計上する
                expenses_maint = (  # 維持費を計上する
                    inforce_beg * model_point.sum_assured * loadings.beta if is_premium_year else 0.0
                )  # 払込期間のみ計上する
                expenses_coll = (  # 集金費を計上する
                    inforce_beg * premiums.gross_annual_premium * loadings.gamma
                    if is_premium_year
                    else 0.0
                )  # 払込期間のみ計上する
            expenses_total = expenses_acq + expenses_maint + expenses_coll  # 総費用を合算する

            reserve_begin = tV_valuation[t] * model_point.sum_assured  # 期首準備金
            reserve_end = tV_valuation[t + 1] * model_point.sum_assured  # 期末準備金
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

            spot_df = (1.0 / (1.0 + spot_rate)) ** (t + 1)  # 割引係数を計算する
            pv_net_cf = net_cf * spot_df  # 割引現在価値を計算する
            pv_loading = loading_income * spot_df  # loadingの現価を計算する
            pv_expense = expenses_total * spot_df  # 費用の現価を計算する
            records.append(  # 行データを追加する
                {
                    "t": t,  # 期数
                    "inforce_begin": inforce_beg,  # 期首保有率
                    "inforce_end": inforce_end_t,  # 期末保有率
                    "q_t": q_t,  # 死亡率
                    "lapse_t": w_t,  # 失効率
                    "premium_income": premium_income,  # 保険料収入
                    "net_premium_income": net_premium_income,  # 純保険料収入
                    "loading_income": loading_income,  # loading収入
                    "death_benefit": death_benefit,  # 死亡給付
                    "surrender_benefit": surrender_benefit,  # 解約返戻金
                    "maturity_benefit": maturity_benefit,  # 満期給付
                    "expenses_acq": expenses_acq,  # 獲得費
                    "expenses_maint": expenses_maint,  # 維持費
                    "expenses_coll": expenses_coll,  # 集金費
                    "expenses_total": expenses_total,  # 総費用
                    "reserve_begin": reserve_begin,  # 期首準備金
                    "reserve_end": reserve_end,  # 期末準備金
                    "reserve_change": reserve_change,  # 準備金増減
                    "investment_income": investment_income,  # 運用収益
                    "net_cf": net_cf,  # 純キャッシュフロー
                    "spot_rate": spot_rate,  # スポットレート
                    "forward_rate": forward_rate,  # フォワードレート
                    "spot_df": spot_df,  # 割引係数
                    "pv_net_cf": pv_net_cf,  # 割引現在価値
                    "pv_loading": pv_loading,  # loading現価
                    "pv_expense": pv_expense,  # 費用現価
                }
            )  # 行追加

        cashflow = pd.DataFrame(records)  # 行リストをDataFrameに変換する
        irr = calc_irr(cashflow["net_cf"].tolist())  # IRRを計算する
        new_business_value = float(cashflow["pv_net_cf"].sum())  # NBVを計算する
        pv_loading = float(cashflow["pv_loading"].sum())  # loading現価の合計
        pv_expense = float(cashflow["pv_expense"].sum())  # 費用現価の合計
        loading_surplus = pv_loading - pv_expense  # 充足額を計算する
        premium_total = float(premiums.gross_annual_premium * model_point.premium_paying_years)  # 総払込保険料
        premium_to_maturity_ratio = premium_total / float(model_point.sum_assured)  # PTM比率を計算する

        results.append(  # モデルポイント結果を追加する
            ProfitTestResult(  # 結果オブジェクトを構築する
                model_point=model_point,  # モデルポイント
                loadings=loadings,  # alpha/beta/gamma
                cashflow=cashflow,  # キャッシュフロー表
                irr=irr,  # IRR
                new_business_value=new_business_value,  # NBV
                premiums=premiums,  # 保険料計算結果
                pv_loading=pv_loading,  # loading現価
                pv_expense=pv_expense,  # 費用現価
                loading_surplus=loading_surplus,  # 充足額
                premium_total=premium_total,  # 総払込
                premium_to_maturity_ratio=premium_to_maturity_ratio,  # PTM比率
            )  # 結果オブジェクト
        )  # リストに追加

    summary = _build_summary(results)  # サマリ表を作成する
    return ProfitTestBatchResult(  # バッチ結果をまとめて返す
        results=results,  # モデルポイント結果
        summary=summary,  # サマリ表
        expense_assumptions=expense_assumptions,  # 費用前提
    )  # バッチ結果を返す
