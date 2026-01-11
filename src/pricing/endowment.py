from __future__ import annotations  # 型注釈の前方参照を許可し、循環参照を避けやすくするため

"""
Endowment present value and premium calculations.

Notation
- x: issue age (years)
- n: term years
- m: premium paying years
- i: annual interest rate
- v = 1 / (1 + i)
- q_{x+t}: annual mortality rate
- p_{x:t}: survival probability from age x to t years (p_{x:0} = 1)

Formulas
- A_death = sum v^(t+0.5) * p_{x:t} * q_{x+t}
- A_maturity = v^n * p_{x:n}
- A = A_death + A_maturity
- a = sum v^t * p_{x:t} (annuity due)
- net_rate = A / a
- gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)
"""

from dataclasses import dataclass  # 保険料計算で使うパラメータを不変データとしてまとめるため

from .commutation import build_mortality_q_by_age, survival_probabilities  # 死亡率と生存確率の計算を再利用するため


@dataclass(frozen=True)  # 係数群を意図せず変更しないために不変のデータクラスにする
class LoadingFunctionParams:  # モデルポイントごとのalpha/beta/gammaを作る係数をまとめる入れ物
    """
    Parameters for alpha/beta/gamma loading function.

    Units
    - a0, a_age, a_term, a_sex: alpha components (per 1 sum assured)
    - b0, b_age, b_term, b_sex: beta components (per 1 sum assured)
    - g0, g_term: gamma components (rate)
    """

    a0: float  # alphaの基礎項として全体水準を調整する
    a_age: float  # alphaの年齢感応度として年齢差を反映する
    a_term: float  # alphaの期間感応度として保険期間差を反映する
    a_sex: float  # alphaの性別感応度として男女差を反映する
    b0: float  # betaの基礎項として全体水準を調整する
    b_age: float  # betaの年齢感応度として年齢差を反映する
    b_term: float  # betaの期間感応度として保険期間差を反映する
    b_sex: float  # betaの性別感応度として男女差を反映する
    g0: float  # gammaの基礎項として全体水準を調整する
    g_term: float  # gammaの期間感応度として保険期間差を反映する


@dataclass(frozen=True)  # 計算済みの負荷率を安定して扱うための不変データクラス
class LoadingParameters:  # alpha/beta/gammaの実値を保持するための入れ物
    """
    Generated alpha/beta/gamma loading parameters.

    Units
    - alpha, beta: per 1 sum assured
    - gamma: rate
    """

    alpha: float  # 獲得費などに対応するalpha負荷の実値
    beta: float  # 維持費などに対応するbeta負荷の実値
    gamma: float  # 集金費などに対応するgamma負荷の実値


@dataclass(frozen=True)  # 計算結果をまとめて返すための不変データクラス
class EndowmentPremiums:  # 養老保険の保険料計算結果を束ねる
    """
    Endowment calculation results.

    Units
    - A, a: present value factors per unit sum assured
    - net_rate / gross_rate: annual premium rate
    - net_annual_premium / gross_annual_premium / monthly_premium: JPY
    """

    A: float  # 死亡・満期を合わせた給付の現価係数
    a: float  # 保険料の年金現価係数
    net_rate: float  # 純保険料率
    gross_rate: float  # 付加保険料を含む総保険料率
    net_annual_premium: int  # 年払純保険料（円、四捨五入）
    gross_annual_premium: int  # 年払総保険料（円、四捨五入）
    monthly_premium: int  # 月払換算（円、四捨五入）


def calc_loading_parameters(  # モデルポイントごとのalpha/beta/gammaを生成する入口
    params: LoadingFunctionParams,  # 係数関数のパラメータ一式
    issue_age: int,  # 被保険者の加入年齢
    term_years: int,  # 保険期間
    sex: str,  # 性別（male/female）
) -> LoadingParameters:  # 計算済みの負荷率を返すことで次工程の保険料計算に渡す
    """
    Generate alpha/beta/gamma for the model point.

    Units
    - issue_age: years
    - term_years: years
    - sex: "male" / "female"
    - params are function coefficients (not a premium scaling factor)
    """
    sex_indicator = 1.0 if sex == "female" else 0.0  # 性別を数値化して係数計算に使う
    age_delta = float(issue_age - 30)  # 基準年齢との差分を取り、直線項として扱う
    term_delta = float(term_years - 10)  # 基準期間との差分を取り、直線項として扱う

    alpha = params.a0 + params.a_age * age_delta + params.a_term * term_delta + params.a_sex * sex_indicator  # alphaを線形関数で算出する
    beta = params.b0 + params.b_age * age_delta + params.b_term * term_delta + params.b_sex * sex_indicator  # betaを線形関数で算出する
    gamma_raw = params.g0 + params.g_term * term_delta  # gammaは期間で変動する前提のため一次式で算出する
    gamma = min(max(gamma_raw, 0.0), 0.5)  # gammaが極端にならないよう上限下限を設ける

    return LoadingParameters(alpha=alpha, beta=beta, gamma=gamma)  # 計算結果をまとめて返す


def calc_endowment_factors(  # 養老保険のAとaを求めることで純保険料率の土台を作る
    q_by_age: dict[int, float],  # 年齢別死亡率の辞書
    issue_age: int,  # 被保険者の加入年齢
    term_years: int,  # 保険期間
    premium_paying_years: int,  # 保険料払込期間
    interest_rate: float,  # 予定利率
) -> tuple[float, float]:  # A（給付現価係数）とa（年金現価係数）を返す
    """
    Calculate A and a for an endowment product.

    Units
    - interest_rate: annual rate (e.g., 0.01 for 1%)
    - term_years / premium_paying_years: years
    """
    if term_years <= 0:  # 保険期間が不正なら計算が成立しないため早期に止める
        raise ValueError("term_years must be positive.")  # ルール違反を明示する
    if premium_paying_years <= 0:  # 払込期間が不正なら保険料の現価が計算できない
        raise ValueError("premium_paying_years must be positive.")  # 入力不備を例外で通知する

    horizon = max(term_years, premium_paying_years)  # 生存確率の計算に必要な最大期間を決める
    p = survival_probabilities(q_by_age, issue_age, horizon)  # 年齢別死亡率から生存確率系列を作る
    v = 1.0 / (1.0 + interest_rate)  # 割引係数の基礎となるvを計算する

    death_pv = 0.0  # 死亡給付の現価合計を初期化する
    for t in range(term_years):  # 保険期間の各年を走査して死亡給付現価を積み上げる
        age = issue_age + t  # 対象年の年齢を求める
        death_pv += (v ** (t + 0.5)) * p[t] * q_by_age[age]  # 中間死亡を想定した現価を加算する

    maturity_pv = (v ** term_years) * p[term_years]  # 満期給付の現価を算出する
    A = death_pv + maturity_pv  # 死亡と満期を合わせた給付現価係数を得る

    annuity = 0.0  # 保険料の年金現価係数を初期化する
    for t in range(premium_paying_years):  # 払込期間の各年を走査して年金現価を積む
        annuity += (v ** t) * p[t]  # 年金現価を1年分加算する

    return A, annuity  # Aとaをまとめて返す


def calc_endowment_premiums(  # 入力前提から純保険料と総保険料を計算する主関数
    mortality_rows,  # CSV由来の死亡率テーブル行
    sex: str,  # 性別（male/female）
    issue_age: int,  # 加入年齢
    term_years: int,  # 保険期間
    premium_paying_years: int,  # 払込期間
    interest_rate: float,  # 予定利率
    sum_assured: int,  # 保険金額
    alpha: float,  # 獲得費相当の負荷係数
    beta: float,  # 維持費相当の負荷係数
    gamma: float,  # 集金費相当の負荷係数
) -> EndowmentPremiums:  # 保険料計算の成果物をまとめて返す
    """
    Calculate endowment premium rates and rounded premiums.

    Units
    - sum_assured: JPY
    - alpha / beta / gamma: annual loading coefficients
    - sex: "male" / "female"
    """
    q_by_age = build_mortality_q_by_age(mortality_rows, sex)  # 死亡率テーブルから年齢別qを構築する
    A, annuity = calc_endowment_factors(  # 給付現価Aと年金現価aを求める
        q_by_age=q_by_age,  # 死亡率辞書を渡す
        issue_age=issue_age,  # 加入年齢を渡す
        term_years=term_years,  # 保険期間を渡す
        premium_paying_years=premium_paying_years,  # 払込期間を渡す
        interest_rate=interest_rate,  # 予定利率を渡す
    )  # 係数計算の結果を受け取る
    if annuity <= 0.0:  # 年金現価が非正なら保険料率が計算できない
        raise ValueError("Premium annuity factor must be positive.")  # 入力前提の異常を通知する

    net_rate = A / annuity  # 純保険料率を算出する
    gross_rate = (net_rate + alpha / annuity + beta) / (1.0 - gamma)  # 付加保険料を含めた総保険料率を算出する

    net_annual = int(round(net_rate * sum_assured, 0))  # 純保険料を円単位に丸める
    gross_annual = int(round(gross_rate * sum_assured, 0))  # 総保険料を円単位に丸める
    monthly = int(round(gross_annual / 12.0, 0))  # 年払を月払に換算して丸める

    return EndowmentPremiums(  # 計算結果をデータクラスにまとめて返す
        A=A,  # 給付現価係数を設定する
        a=annuity,  # 年金現価係数を設定する
        net_rate=net_rate,  # 純保険料率を設定する
        gross_rate=gross_rate,  # 総保険料率を設定する
        net_annual_premium=net_annual,  # 年払純保険料を設定する
        gross_annual_premium=gross_annual,  # 年払総保険料を設定する
        monthly_premium=monthly,  # 月払保険料を設定する
    )  # 結果を返す
