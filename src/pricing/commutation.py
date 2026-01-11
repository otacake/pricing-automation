from __future__ import annotations  # 型注釈の前方参照を可能にし、循環参照を避けるため

"""
Commutation helpers for survival probabilities.

Notation
- x: issue age (years)
- t: elapsed years
- q_{x+t}: annual mortality rate
- p_{x:t}: survival probability from age x to t years (p_{x:0}=1)
"""

from dataclasses import dataclass  # 死亡率行の構造を明確にするため
import math  # NaN判定など数値処理に使うため
from typing import Iterable, Mapping, Protocol  # 型注釈で入出力の期待形を示すため


class _RowLike(Protocol):  # DataFrame行やdictなど、行アクセスの共通インタフェースを表す
    def __getitem__(self, key: str) -> object: ...  # 辞書アクセス互換であることを示す


@dataclass(frozen=True)  # 死亡率テーブルの1行を安全に保持するため
class MortalityRow:  # CSV行の意味を明確にするためのデータクラス
    """
    One mortality table row.

    Units
    - age: years
    - q_male / q_female: annual mortality rate (e.g., 0.003)
    """

    age: int  # 年齢（整数）
    q_male: float | None  # 男性の死亡率
    q_female: float | None  # 女性の死亡率


def _get_field(row: object, key: str) -> object:  # 行がdictか属性かに関わらず値を取得するため
    if isinstance(row, Mapping):  # dictライクな行ならキー参照を使う
        return row.get(key)  # 指定キーの値を返す
    return getattr(row, key, None)  # 属性アクセスで値を取得する


def _coerce_float(value: object) -> float | None:  # 数値や文字列を安全にfloatへ変換するため
    if value is None or isinstance(value, bool):  # Noneやboolは無効値として扱う
        return None  # 無効値としてNoneを返す
    if isinstance(value, (int, float)):  # 数値ならそのまま扱う
        if isinstance(value, float) and math.isnan(value):  # NaNは無効値として除外する
            return None  # NaNは使えないのでNoneを返す
        return float(value)  # 数値をfloatに揃える
    if isinstance(value, str):  # 文字列ならトリムして数値化を試す
        text = value.strip()  # 前後の空白を除去する
        if not text:  # 空文字列は無効
            return None  # 変換せずNoneを返す
        try:  # 文字列の数値変換を試みる
            return float(text)  # 数値変換に成功した値を返す
        except ValueError:  # 数値変換できない場合
            return None  # 無効値としてNoneを返す
    return None  # その他の型は対象外としてNoneを返す


def _coerce_int(value: object) -> int | None:  # 数値や文字列を安全にintへ変換するため
    if value is None or isinstance(value, bool):  # Noneやboolは無効値として扱う
        return None  # 無効値としてNoneを返す
    if isinstance(value, (int, float)):  # 数値なら四捨五入して整数化する
        if isinstance(value, float) and math.isnan(value):  # NaNは無効
            return None  # NaNは使えないのでNoneを返す
        return int(round(float(value)))  # 数値を丸めてintにする
    if isinstance(value, str):  # 文字列なら数値化を試す
        text = value.strip()  # 前後の空白を除去する
        if not text:  # 空文字列は無効
            return None  # 無効値としてNoneを返す
        try:  # 文字列の数値変換を試みる
            return int(round(float(text)))  # 数値変換後に整数化して返す
        except ValueError:  # 数値変換できない場合
            return None  # 無効値としてNoneを返す
    return None  # その他の型は対象外としてNoneを返す


def build_mortality_q_by_age(  # 死亡率テーブルから年齢→死亡率の辞書を作る
    mortality_rows: Iterable[MortalityRow | Mapping[str, object]],  # 行データの集合
    sex: str,  # 性別（male/female）
) -> dict[int, float]:  # 年齢をキーに死亡率を返す辞書
    """
    Build an age-to-q mapping for the given sex.

    Units
    - sex: "male" / "female"
    - q: annual mortality rate
    """
    sex_key = {"male": "q_male", "female": "q_female"}.get(sex)  # 性別に対応する列名を選ぶ
    if sex_key is None:  # 対応外の性別なら処理できない
        raise ValueError(f"Unsupported sex: {sex}")  # 入力の誤りを明示する

    q_by_age: dict[int, float] = {}  # 結果の辞書を初期化する
    for row in mortality_rows:  # 行データを順に処理する
        age = _coerce_int(_get_field(row, "age"))  # 年齢を整数として取得する
        if age is None:  # 年齢が取得できない行はスキップする
            continue  # 次の行へ進む
        q_value = _coerce_float(_get_field(row, sex_key))  # 性別に対応する死亡率を取得する
        if q_value is None:  # 死亡率が欠損ならスキップする
            continue  # 次の行へ進む
        q_by_age[age] = q_value  # 年齢→死亡率の対応を登録する
    return q_by_age  # 年齢別死亡率の辞書を返す


def survival_probabilities(  # 生存確率系列を作ることで保険料計算に使えるようにする
    q_by_age: Mapping[int, float],  # 年齢別死亡率
    issue_age: int,  # 加入年齢
    years: int,  # 期間
) -> list[float]:  # p_{x:t} の系列を返す
    """
    Build survival probabilities p_{x:t}.

    Units
    - issue_age: years
    - years: years
    - q_by_age: annual mortality rate by age
    """
    if years < 0:  # マイナス期間は不正
        raise ValueError("years must be non-negative.")  # 入力の誤りを通知する

    probs = [1.0]  # t=0の生存確率は必ず1
    for t in range(years):  # 期間分だけ生存確率を更新する
        age = issue_age + t  # t年後の年齢を求める
        if age not in q_by_age:  # 対象年齢の死亡率が欠落している場合
            raise ValueError(f"Missing mortality rate for age {age}.")  # 欠損を明示する
        q_value = q_by_age[age]  # 年齢に対応する死亡率を取得する
        probs.append(probs[-1] * (1.0 - q_value))  # 生存確率を更新して追加する
    return probs  # 生存確率系列を返す
