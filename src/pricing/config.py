from __future__ import annotations  # 型注釈の前方参照を許可し、循環参照を避けるため

"""
Configuration helpers for pricing automation.
"""

from dataclasses import dataclass  # 設定構造を明確にするため
from typing import Mapping, Sequence  # 設定の型を注釈するため

from .endowment import LoadingFunctionParams  # loading係数のデータ型を共有するため


def _load_loading_params_from_mapping(  # dictからloading係数を読み取る内部関数
    params_cfg: Mapping[str, object] | None,  # YAMLなどの読み込み結果
    defaults: LoadingFunctionParams,  # デフォルト値の集合
) -> LoadingFunctionParams:  # 係数一式を返す
    def _get_value(key: str, default: float) -> float:  # 値の有無を吸収しfloat化する小関数
        if params_cfg is None:  # 設定がない場合はデフォルトを使う
            return float(default)  # デフォルト値をfloatに変換して返す
        raw = params_cfg.get(key, default)  # 指定キーがなければデフォルトを使う
        return float(raw)  # 数値に変換して返す

    return LoadingFunctionParams(  # 全係数を組み立てて返す
        a0=_get_value("a0", defaults.a0),  # alpha基礎項を読み込む
        a_age=_get_value("a_age", defaults.a_age),  # alpha年齢項を読み込む
        a_term=_get_value("a_term", defaults.a_term),  # alpha期間項を読み込む
        a_sex=_get_value("a_sex", defaults.a_sex),  # alpha性別項を読み込む
        b0=_get_value("b0", defaults.b0),  # beta基礎項を読み込む
        b_age=_get_value("b_age", defaults.b_age),  # beta年齢項を読み込む
        b_term=_get_value("b_term", defaults.b_term),  # beta期間項を読み込む
        b_sex=_get_value("b_sex", defaults.b_sex),  # beta性別項を読み込む
        g0=_get_value("g0", defaults.g0),  # gamma基礎項を読み込む
        g_term=_get_value("g_term", defaults.g_term),  # gamma期間項を読み込む
    )  # LoadingFunctionParams を返す


def read_loading_parameters(  # 設定全体からloading係数を抽出する入口
    config: Mapping[str, object],  # YAML読み込み後の設定
) -> LoadingFunctionParams | None:  # 係数がなければNone
    """
    Read loading function parameters from config.

    These parameters define the alpha/beta/gamma functions used to build
    loadings, not a direct premium scaling factor.
    """
    defaults = LoadingFunctionParams(  # 係数のデフォルト値を定義する
        a0=0.03,  # alpha基礎
        a_age=0.0,  # alpha年齢
        a_term=0.0,  # alpha期間
        a_sex=0.0,  # alpha性別
        b0=0.007,  # beta基礎
        b_age=0.0,  # beta年齢
        b_term=0.0,  # beta期間
        b_sex=0.0,  # beta性別
        g0=0.03,  # gamma基礎
        g_term=0.0,  # gamma期間
    )  # デフォルト値の集合

    if "loading_parameters" in config:  # 直接指定された係数があれば最優先で読む
        params_cfg = config.get("loading_parameters")  # セクションを取得する
        if isinstance(params_cfg, Mapping):  # dict形式なら内容を読み込む
            return _load_loading_params_from_mapping(params_cfg, defaults)  # 係数を組み立てて返す
        return defaults  # 形式不一致でもキーがある場合はデフォルトを使う

    loading_cfg = config.get("loading_function")  # 旧形式または別形式の設定を読む
    if isinstance(loading_cfg, Mapping):  # dict形式なら読む
        params_cfg = loading_cfg.get("params")  # params内に係数がある形式を想定する
        if isinstance(params_cfg, Mapping):  # paramsがdictならそれを読む
            return _load_loading_params_from_mapping(params_cfg, defaults)  # paramsを係数として読む
        return _load_loading_params_from_mapping(loading_cfg, defaults)  # paramsが無ければ直下を読む

    return None  # 係数の指定が無ければNone


@dataclass(frozen=True)  # 最適化段階の設定を不変で扱う
class OptimizationStage:  # 最適化を段階的に進めるための定義
    """
    One optimization stage definition.

    Units
    - variables: loading function coefficient names
    """

    name: str  # 段階名
    variables: list[str]  # この段階で探索する係数名


@dataclass(frozen=True)  # 探索範囲の設定を不変で扱う
class OptimizationBounds:  # 係数ごとの探索範囲を表す
    """
    Bounds definition for one coefficient.

    Units
    - min/max: coefficient value
    - step: coefficient step
    """

    min: float  # 探索下限
    max: float  # 探索上限
    step: float  # 探索ステップ


@dataclass(frozen=True)  # 最適化設定をまとめて扱う
class OptimizationSettings:  # hard/soft制約や探索設定を集約する
    """
    Optimization settings for hard/soft constraints and search.

    Units
    - irr_hard/irr_target: annual rate
    - loading_surplus_hard: JPY
    - loading_surplus_hard_ratio: ratio per sum assured
    - premium_to_maturity_hard_max/target: ratio
    - nbv_hard: JPY
    - l2_lambda: weight for L2 regularization
    - max_iterations_per_stage: iteration count
    - watch_model_point_ids: model points excluded from objective/constraints
    - objective_mode: optimization objective mode
    - premium_to_maturity_soft_min: soft minimum for premium ratio (tie-break)
    """

    irr_hard: float  # IRRのハード下限
    irr_target: float  # IRRのソフト目標
    loading_surplus_hard: float  # 費用充足額のハード下限
    loading_surplus_hard_ratio: float | None  # 費用充足比率のハード下限
    premium_to_maturity_hard_max: float  # premium-to-maturityの上限
    premium_to_maturity_target: float  # premium-to-maturityのソフト目標
    nbv_hard: float  # NBVのハード下限
    stages: list[OptimizationStage]  # 段階的探索の定義
    bounds: dict[str, OptimizationBounds]  # 係数ごとの探索範囲
    l2_lambda: float  # L2正則化の重み
    max_iterations_per_stage: int  # 各段階の探索回数上限
    watch_model_point_ids: list[str]  # hard制約から除外するモデルポイント
    objective_mode: str  # 目的関数モード
    premium_to_maturity_soft_min: float | None  # soft最小値（同点時の判定用）


@dataclass(frozen=True)  # 免除スイープ設定を不変で扱う
class ExemptionSweepSettings:  # exemption時のsweep範囲設定
    """
    Sweep settings for exemption policy.

    Units
    - start/end/step: premium_to_maturity ratio
    - irr_threshold: annual rate
    """

    start: float  # スイープ開始値
    end: float  # スイープ終了値
    step: float  # スイープ刻み
    irr_threshold: float  # IRRの閾値


@dataclass(frozen=True)  # 免除設定を不変で扱う
class ExemptionSettings:  # exemption機能の設定全体
    """
    Exemption policy settings for optimization.

    Units
    - enabled: policy switch
    - method: exemption method name
    """

    enabled: bool  # 免除機能の有効/無効
    method: str  # 免除方法の名前
    sweep: ExemptionSweepSettings  # スイープの詳細設定


def load_optimization_settings(config: Mapping[str, object]) -> OptimizationSettings:  # YAMLから最適化設定を読み込む
    """
    Load optimization settings with defaults.
    """
    defaults = {  # 設定が無い場合のデフォルト値
        "irr_hard": 0.07,  # IRRハード下限
        "irr_target": 0.08,  # IRRターゲット
        "loading_surplus_hard": 0.0,  # 費用充足下限（額）
        "loading_surplus_hard_ratio": -0.10,  # 費用充足下限（比率）
        "premium_to_maturity_hard_max": 1.05,  # premium-to-maturity上限
        "premium_to_maturity_target": 1.0,  # premium-to-maturity目標
        "nbv_hard": 0.0,  # NBV下限
        "l2_lambda": 0.1,  # L2重み
        "max_iterations_per_stage": 5000,  # 探索上限
        "watch_model_point_ids": [],  # 監視対象のモデルポイント
        "objective_mode": "penalty",  # 目的関数モード
        "premium_to_maturity_soft_min": None,  # soft最小値
    }  # デフォルト設定の辞書

    constraints_cfg = config.get("constraints", {}) if isinstance(config, Mapping) else {}  # 制約の旧設定を読み込む
    expense_cfg = config.get("expense_sufficiency", {}) if isinstance(config, Mapping) else {}  # 費用充足設定を読み込む
    optimization_cfg = config.get("optimization", {}) if isinstance(config, Mapping) else {}  # 最適化設定を取得する
    if not isinstance(optimization_cfg, Mapping):  # 形式が不正なら空として扱う
        optimization_cfg = {}  # 不正形式を空に置き換える

    irr_hard = optimization_cfg.get(  # IRRハード下限を読み込む
        "irr_hard", constraints_cfg.get("irr_min", defaults["irr_hard"])  # 旧キーを優先しつつデフォルトを使う
    )  # IRRハード下限の値
    irr_target = optimization_cfg.get("irr_target", defaults["irr_target"])  # IRRターゲットを読み込む
    loading_surplus_hard = optimization_cfg.get(  # 費用充足の下限を読み込む
        "loading_surplus_hard", expense_cfg.get("threshold", defaults["loading_surplus_hard"])  # 旧設定と互換
    )  # 充足額の下限
    loading_surplus_hard_ratio = optimization_cfg.get(  # 充足比率の下限を読み込む
        "loading_surplus_hard_ratio", defaults["loading_surplus_hard_ratio"]  # デフォルトと互換
    )  # 充足比率の下限
    premium_to_maturity_hard_max = optimization_cfg.get(  # premium-to-maturity上限を読み込む
        "premium_to_maturity_hard_max", defaults["premium_to_maturity_hard_max"]  # デフォルトを使用
    )  # 上限値
    premium_to_maturity_target = optimization_cfg.get(  # premium-to-maturityターゲット
        "premium_to_maturity_target", defaults["premium_to_maturity_target"]  # デフォルトと互換
    )  # 目標値
    nbv_hard = optimization_cfg.get("nbv_hard", defaults["nbv_hard"])  # NBV下限
    l2_lambda = optimization_cfg.get("l2_lambda", defaults["l2_lambda"])  # L2重み
    max_iterations_per_stage = optimization_cfg.get(  # 探索回数上限
        "max_iterations_per_stage", defaults["max_iterations_per_stage"]  # デフォルトと互換
    )  # 上限値
    objective_cfg = optimization_cfg.get("objective", {})  # 目的関数設定を取得する
    if not isinstance(objective_cfg, Mapping):  # 形式が不正なら空にする
        objective_cfg = {}  # 不正形式を空に置き換える
    objective_mode = objective_cfg.get("mode", defaults["objective_mode"])  # 目的関数モードを取得する
    premium_to_maturity_soft_min = optimization_cfg.get(  # soft最小値を取得する
        "premium_to_maturity_soft_min", defaults["premium_to_maturity_soft_min"]  # デフォルトと互換
    )  # soft最小値
    watch_ids = optimization_cfg.get(  # 監視対象モデルポイントの一覧
        "watch_model_point_ids", defaults["watch_model_point_ids"]  # デフォルトと互換
    )  # 監視対象の一覧
    if not isinstance(watch_ids, Sequence) or isinstance(watch_ids, (str, bytes)):  # 文字列や不正形式を排除する
        watch_ids = []  # 不正な場合は空リストにする

    stage_defs = optimization_cfg.get("stages")  # 探索ステージ定義を取得する
    if not isinstance(stage_defs, Sequence):  # 未設定ならデフォルト定義を使う
        stage_defs = [  # デフォルトの段階定義
            {"name": "base", "variables": ["a0", "b0", "g0"]},  # ベース係数の探索
            {  # 年齢・期間の感応度を追加する段階
                "name": "age_term",  # ステージ名
                "variables": [  # 対象となる係数一覧
                    "a0",  # alpha基礎
                    "b0",  # beta基礎
                    "g0",  # gamma基礎
                    "a_age",  # alpha年齢
                    "a_term",  # alpha期間
                    "b_age",  # beta年齢
                    "b_term",  # beta期間
                    "g_term",  # gamma期間
                ],  # 探索係数の一覧
            },  # 年齢・期間段階の定義
            {  # 性別係数も含める段階
                "name": "sex",  # ステージ名
                "variables": [  # 対象となる係数一覧
                    "a0",  # alpha基礎
                    "b0",  # beta基礎
                    "g0",  # gamma基礎
                    "a_age",  # alpha年齢
                    "a_term",  # alpha期間
                    "b_age",  # beta年齢
                    "b_term",  # beta期間
                    "g_term",  # gamma期間
                    "a_sex",  # alpha性別
                    "b_sex",  # beta性別
                ],  # 探索係数の一覧
            },  # 性別段階の定義
        ]  # デフォルト段階

    stages: list[OptimizationStage] = []  # 最終的なステージ一覧を作る
    for stage in stage_defs:  # 各ステージ定義を処理する
        if not isinstance(stage, Mapping):  # dictでなければスキップする
            continue  # 次の定義へ
        name = str(stage.get("name", "stage"))  # ステージ名を取得する
        variables = stage.get("variables", [])  # 係数一覧を取得する
        if not isinstance(variables, Sequence):  # 形式が不正なら空にする
            variables = []  # 不正形式を空に置き換える
        stages.append(  # 構造化して追加する
            OptimizationStage(  # ステージのデータクラスを作る
                name=name,  # ステージ名
                variables=[str(var) for var in variables],  # 係数名を文字列に揃える
            )  # ステージを構築
        )  # リストに追加

    default_bounds = {  # 係数ごとのデフォルト探索範囲
        "a0": OptimizationBounds(min=0.0, max=0.1, step=0.002),  # alpha基礎
        "a_age": OptimizationBounds(min=-0.005, max=0.005, step=0.0005),  # alpha年齢
        "a_term": OptimizationBounds(min=-0.005, max=0.005, step=0.0005),  # alpha期間
        "a_sex": OptimizationBounds(min=-0.01, max=0.01, step=0.001),  # alpha性別
        "b0": OptimizationBounds(min=0.0, max=0.05, step=0.001),  # beta基礎
        "b_age": OptimizationBounds(min=-0.002, max=0.002, step=0.0002),  # beta年齢
        "b_term": OptimizationBounds(min=-0.002, max=0.002, step=0.0002),  # beta期間
        "b_sex": OptimizationBounds(min=-0.01, max=0.01, step=0.001),  # beta性別
        "g0": OptimizationBounds(min=0.0, max=0.2, step=0.005),  # gamma基礎
        "g_term": OptimizationBounds(min=-0.02, max=0.02, step=0.002),  # gamma期間
    }  # デフォルト範囲の辞書

    bounds_cfg = optimization_cfg.get("bounds", {}) if isinstance(optimization_cfg, Mapping) else {}  # 上書き範囲設定を取得
    bounds: dict[str, OptimizationBounds] = {}  # 最終的な範囲を格納する
    for key, default in default_bounds.items():  # 各係数のデフォルト範囲を走査
        override = bounds_cfg.get(key, {})  # 上書き設定を取得する
        if isinstance(override, Mapping):  # dictであれば上書き適用
            bounds[key] = OptimizationBounds(  # 上書き込みで範囲を作る
                min=float(override.get("min", default.min)),  # 下限を上書き
                max=float(override.get("max", default.max)),  # 上限を上書き
                step=float(override.get("step", default.step)),  # 刻みを上書き
            )  # 上書きした範囲
        else:  # 上書きが無効ならデフォルトを使う
            bounds[key] = default  # デフォルト範囲を採用

    return OptimizationSettings(  # 設定をデータクラスにまとめる
        irr_hard=float(irr_hard),  # IRRハード下限
        irr_target=float(irr_target),  # IRRターゲット
        loading_surplus_hard=float(loading_surplus_hard),  # 費用充足下限（額）
        loading_surplus_hard_ratio=(  # 費用充足下限（比率）
            None if loading_surplus_hard_ratio is None else float(loading_surplus_hard_ratio)
        ),  # Noneなら比率制約なし
        premium_to_maturity_hard_max=float(premium_to_maturity_hard_max),  # premium-to-maturity上限
        premium_to_maturity_target=float(premium_to_maturity_target),  # premium-to-maturity目標
        nbv_hard=float(nbv_hard),  # NBV下限
        stages=stages,  # ステージ定義
        bounds=bounds,  # 探索範囲
        l2_lambda=float(l2_lambda),  # L2重み
        max_iterations_per_stage=int(max_iterations_per_stage),  # 探索回数上限
        watch_model_point_ids=[str(item) for item in watch_ids],  # 監視対象を文字列に揃える
        objective_mode=str(objective_mode),  # 目的関数モード
        premium_to_maturity_soft_min=(  # soft最小値
            None
            if premium_to_maturity_soft_min is None
            else float(premium_to_maturity_soft_min)
        ),  # Noneならsoft最小値なし
    )  # 設定を返す


def load_exemption_settings(config: Mapping[str, object]) -> ExemptionSettings:  # 免除設定を読み込む
    """
    Load exemption policy settings with defaults.
    """
    defaults = {  # デフォルト設定
        "enabled": False,  # 免除無効
        "method": "sweep_ptm",  # 免除方式
        "sweep": {  # sweepのデフォルト
            "start": 1.0,  # 開始値
            "end": 1.05,  # 終了値
            "step": 0.01,  # 刻み
            "irr_threshold": 0.0,  # IRR閾値
        },  # sweep設定
    }  # デフォルト設定

    optimization_cfg = config.get("optimization", {}) if isinstance(config, Mapping) else {}  # 最適化設定を取得
    exemption_cfg = optimization_cfg.get("exemption", {}) if isinstance(optimization_cfg, Mapping) else {}  # 免除設定を取得
    if not isinstance(exemption_cfg, Mapping):  # 形式不正なら空にする
        exemption_cfg = {}  # 不正形式を空に置き換える

    enabled = bool(exemption_cfg.get("enabled", defaults["enabled"]))  # 有効/無効を取得する
    method = str(exemption_cfg.get("method", defaults["method"]))  # 方式名を取得する
    sweep_cfg = exemption_cfg.get("sweep", {}) if isinstance(exemption_cfg, Mapping) else {}  # sweep設定を取得
    if not isinstance(sweep_cfg, Mapping):  # 形式不正なら空にする
        sweep_cfg = {}  # 不正形式を空に置き換える

    sweep = ExemptionSweepSettings(  # sweep設定を構造化する
        start=float(sweep_cfg.get("start", defaults["sweep"]["start"])),  # 開始値
        end=float(sweep_cfg.get("end", defaults["sweep"]["end"])),  # 終了値
        step=float(sweep_cfg.get("step", defaults["sweep"]["step"])),  # 刻み
        irr_threshold=float(  # IRR閾値
            sweep_cfg.get("irr_threshold", defaults["sweep"]["irr_threshold"])
        ),  # 閾値
    )  # sweep設定を構築

    return ExemptionSettings(enabled=enabled, method=method, sweep=sweep)  # 免除設定を返す


def loading_surplus_threshold(settings: OptimizationSettings, sum_assured: int) -> float:  # 充足額の閾値を計算する
    """
    Compute loading surplus threshold (JPY) for a model point.
    """
    if settings.loading_surplus_hard_ratio is not None:  # 比率制約があるなら優先する
        return settings.loading_surplus_hard_ratio * float(sum_assured)  # 比率×保険金額で閾値を計算する
    return settings.loading_surplus_hard  # 比率が無ければ固定額の閾値を返す
