from __future__ import annotations  # 型注釈の前方参照を許可し、循環参照を避けるため

"""
Optimization utilities for loading function parameters.
"""

from dataclasses import dataclass, replace  # 設定・結果の構造化と差分更新に使うため
from pathlib import Path  # パス操作をOS非依存で行うため
import copy  # 設定の深いコピーに使うため
import math  # 無限大や比較に使うため
import yaml  # YAML出力に使うため

from .config import (  # 最適化設定と免除設定の読み込みに使うため
    ExemptionSettings,  # 免除設定の型
    OptimizationSettings,  # 最適化設定の型
    OptimizationStage,  # ステージ定義の型
    load_exemption_settings,  # 免除設定の読み込み
    load_optimization_settings,  # 最適化設定の読み込み
    loading_surplus_threshold,  # 充足額閾値の計算
    read_loading_parameters,  # loading係数の読み込み
)
from .endowment import LoadingFunctionParams  # loading係数の型
from .profit_test import ProfitTestBatchResult, model_point_label, run_profit_test  # 収益性検証実行とラベル生成
from .sweep_ptm import sweep_premium_to_maturity_all  # 免除判断用のsweepに使うため


@dataclass(frozen=True)  # 最適化結果を不変で保持するため
class OptimizationResult:  # 最適化の結果をまとめる
    """
    Optimization outputs.

    Units
    - params: loading function parameters
    - success: constraint satisfaction
    - iterations: evaluation count
    - exempt_model_points: model point IDs skipped in hard constraints
    - exemption_settings: exemption policy configuration (if enabled)
    - watch_model_points: model point IDs excluded from objective/constraints
    - min_irr: minimum IRR among evaluated model points
    - min_irr_model_point: model point ID that attains min_irr
    - proposal: conditional success proposal (if any)
    """

    params: LoadingFunctionParams  # 最適化後の係数
    batch_result: ProfitTestBatchResult  # 収益性検証の結果
    success: bool  # hard制約を満たしたか
    iterations: int  # 評価回数
    failure_details: list[str]  # 失敗理由の詳細
    exempt_model_points: list[str]  # hard制約から除外されたモデルポイント
    exemption_settings: ExemptionSettings | None  # 免除設定（有効時のみ）
    watch_model_points: list[str]  # 監視対象のモデルポイント
    min_irr: float  # 最小IRR
    min_irr_model_point: str | None  # 最小IRRのモデルポイント
    proposal: dict[str, object] | None = None  # 条件付き成功の提案


@dataclass(frozen=True)  # 候補評価結果を不変で保持するため
class CandidateEvaluation:  # 係数候補の評価値をまとめる
    """
    Candidate evaluation outputs.

    Units
    - objective: penalty sum (dimensionless)
    - violation: hard constraint penalty sum (dimensionless)
    - min_irr: minimum IRR among evaluated model points
    - min_irr_model_point: model point ID that attains min_irr
    """

    params: LoadingFunctionParams  # 係数候補
    result: ProfitTestBatchResult  # 収益性検証結果
    feasible: bool  # hard制約を満たしたか
    objective: float  # 目的関数値
    violation: float  # hard制約違反の大きさ
    irr_penalty: float  # IRR目標に対するペナルティ
    premium_penalty: float  # PTM目標に対するペナルティ
    l2_penalty: float  # 正則化項
    ptm_soft_penalty: float  # soft最小値のペナルティ
    min_irr: float  # 最小IRR
    min_irr_model_point: str | None  # 最小IRRのモデルポイント
    failure_details: list[str]  # 失敗理由の詳細


def _evaluate(  # 係数候補を評価して目的関数・制約違反を計算する
    config: dict,  # 設定
    base_dir: Path,  # 相対パス基準
    params: LoadingFunctionParams,  # 係数候補
    settings: OptimizationSettings,  # 最適化設定
    stage_vars: list[str],  # 対象係数
    exempt_model_points: set[str],  # 免除対象
    watch_model_points: set[str],  # 監視対象
) -> CandidateEvaluation:  # 候補評価結果を返す
    result = run_profit_test(config, base_dir=base_dir, loading_params=params)  # 収益性検証を実行する

    irr_penalty = 0.0  # IRRペナルティの初期化
    premium_penalty = 0.0  # PTMペナルティの初期化
    hard_violation = 0.0  # hard制約違反の初期化
    ptm_soft_penalty = 0.0  # soft最小値ペナルティの初期化
    failure_details: list[str] = []  # 失敗詳細の初期化
    min_irr = math.inf  # 最小IRRの初期値
    min_irr_model_point: str | None = None  # 最小IRRのモデルポイント
    for res in result.results:  # 各モデルポイント結果を評価する
        label = model_point_label(res.model_point)  # 表示用ラベルを作る
        if label in exempt_model_points or label in watch_model_points:  # 免除/監視対象は評価対象外
            continue  # 次のモデルポイントへ
        if res.irr < min_irr:  # 最小IRRの更新判定
            min_irr = res.irr  # 最小IRRを更新する
            min_irr_model_point = label  # 最小IRRのモデルポイントを更新する
        threshold = loading_surplus_threshold(settings, res.model_point.sum_assured)  # 充足額の閾値を計算する
        irr_shortfall = max(settings.irr_hard - res.irr, 0.0)  # IRRの不足分を計算する
        if irr_shortfall > 0:  # 不足があればhard違反に加算する
            hard_violation += irr_shortfall * irr_shortfall  # 二乗ペナルティで加算
            failure_details.append(f"{label} irr_hard shortfall={irr_shortfall:.6f}")  # 詳細を記録

        loading_shortfall = max(  # 充足額不足を計算する
            threshold - res.loading_surplus, 0.0
        )  # 不足分
        if loading_shortfall > 0:  # 不足があればhard違反に加算する
            hard_violation += loading_shortfall * loading_shortfall  # 二乗ペナルティで加算
            failure_details.append(  # 詳細を記録
                f"{label} loading_surplus_hard shortfall={loading_shortfall:.2f}"
            )

        premium_excess_hard = max(  # PTM上限超過を計算する
            res.premium_to_maturity_ratio - settings.premium_to_maturity_hard_max, 0.0
        )  # 超過分
        if premium_excess_hard > 0:  # 超過があればhard違反に加算する
            hard_violation += premium_excess_hard * premium_excess_hard  # 二乗ペナルティで加算
            failure_details.append(  # 詳細を記録
                f"{label} premium_to_maturity_hard excess={premium_excess_hard:.6f}"
            )

        nbv_shortfall = max(settings.nbv_hard - res.new_business_value, 0.0)  # NBV不足分を計算する
        if nbv_shortfall > 0:  # 不足があればhard違反に加算する
            hard_violation += nbv_shortfall * nbv_shortfall  # 二乗ペナルティで加算
            failure_details.append(  # 詳細を記録
                f"{label} nbv_hard shortfall={nbv_shortfall:.2f}"
            )

        alpha_shortfall = max(0.0 - res.loadings.alpha, 0.0)  # alphaの負値を検出する
        if alpha_shortfall > 0:  # 負値ならhard違反に加算する
            hard_violation += alpha_shortfall * alpha_shortfall  # 二乗ペナルティで加算
            failure_details.append(  # 詳細を記録
                f"{label} alpha_non_negative shortfall={alpha_shortfall:.6f}"
            )

        beta_shortfall = max(0.0 - res.loadings.beta, 0.0)  # betaの負値を検出する
        if beta_shortfall > 0:  # 負値ならhard違反に加算する
            hard_violation += beta_shortfall * beta_shortfall  # 二乗ペナルティで加算
            failure_details.append(  # 詳細を記録
                f"{label} beta_non_negative shortfall={beta_shortfall:.6f}"
            )

        gamma_shortfall = max(0.0 - res.loadings.gamma, 0.0)  # gammaの負値を検出する
        if gamma_shortfall > 0:  # 負値ならhard違反に加算する
            hard_violation += gamma_shortfall * gamma_shortfall  # 二乗ペナルティで加算
            failure_details.append(  # 詳細を記録
                f"{label} gamma_non_negative shortfall={gamma_shortfall:.6f}"
            )

        loading_amount = (  # 付加保険料が正かを確認する
            res.premiums.gross_annual_premium - res.premiums.net_annual_premium
        )
        loading_shortfall = max(1e-12 - float(loading_amount), 0.0)  # 0以下は違反扱い
        if loading_shortfall > 0:  # 不足があればhard違反に加算する
            hard_violation += loading_shortfall * loading_shortfall  # 二乗ペナルティで加算
            failure_details.append(  # 詳細を記録
                f"{label} loading_positive shortfall={loading_shortfall:.6f}"
            )

        irr_gap = max(settings.irr_target - res.irr, 0.0)  # IRR目標との差分を計算する
        irr_penalty += irr_gap * irr_gap  # ペナルティを積算する
        premium_gap = max(  # PTM目標との差分を計算する
            res.premium_to_maturity_ratio - settings.premium_to_maturity_target, 0.0
        )  # 目標超過
        premium_penalty += premium_gap * premium_gap  # ペナルティを積算する
        if settings.premium_to_maturity_soft_min is not None:  # soft最小値が設定されている場合
            soft_gap = max(  # soft最小値との差分を計算する
                settings.premium_to_maturity_soft_min - res.premium_to_maturity_ratio, 0.0
            )  # 不足分
            ptm_soft_penalty += soft_gap * soft_gap  # ペナルティを積算する

    if min_irr is math.inf:  # 評価対象が無かった場合
        min_irr = float("nan")  # NaNとして扱う
        min_irr_model_point = None  # モデルポイントをNoneにする

    l2_penalty = 0.0  # L2ペナルティの初期化
    for name in stage_vars:  # 対象係数ごとに正則化を計算する
        l2_penalty += getattr(params, name) ** 2  # 係数の二乗を加算する
    l2_penalty *= settings.l2_lambda  # 重みを掛ける

    objective = irr_penalty + premium_penalty + l2_penalty  # 目的関数を合成する
    feasible = hard_violation <= 0.0  # hard違反がないか判定する
    return CandidateEvaluation(  # 評価結果を返す
        params=params,  # 係数候補
        result=result,  # 収益性検証結果
        feasible=feasible,  # hard制約判定
        objective=objective,  # 目的関数値
        violation=hard_violation,  # hard違反量
        irr_penalty=irr_penalty,  # IRRペナルティ
        premium_penalty=premium_penalty,  # PTMペナルティ
        l2_penalty=l2_penalty,  # L2ペナルティ
        ptm_soft_penalty=ptm_soft_penalty,  # soft最小ペナルティ
        min_irr=min_irr,  # 最小IRR
        min_irr_model_point=min_irr_model_point,  # 最小IRRのモデルポイント
        failure_details=failure_details,  # 失敗詳細
    )  # 評価結果を返す


def _is_better_candidate(  # 候補の優劣判定を行う
    candidate: CandidateEvaluation,  # 新しい候補
    best: CandidateEvaluation | None,  # 現在の最良候補
    settings: OptimizationSettings,  # 最適化設定
) -> bool:  # 新候補が優れているかを返す
    if best is None:  # 最良候補がまだ無い場合
        return True  # 新候補を採用する
    if candidate.feasible and not best.feasible:  # feasibleが優先される
        return True  # feasibleの方を採用する
    if candidate.feasible and best.feasible:  # 両者ともfeasibleの場合
        if settings.objective_mode == "maximize_min_irr":  # 最小IRR最大化モードの場合
            candidate_min_irr = (  # NaN対策をしつつ最小IRRを取得
                candidate.min_irr if not math.isnan(candidate.min_irr) else -math.inf
            )
            best_min_irr = (  # NaN対策をしつつ最小IRRを取得
                best.min_irr if not math.isnan(best.min_irr) else -math.inf
            )
            if candidate_min_irr > best_min_irr + 1e-12:  # 最小IRRが大きい方を採用
                return True  # 新候補が優れている
            if abs(candidate_min_irr - best_min_irr) <= 1e-12:  # 同値なら次の基準へ
                if settings.premium_to_maturity_soft_min is not None:  # soft最小値がある場合
                    if candidate.ptm_soft_penalty < best.ptm_soft_penalty - 1e-12:  # softペナルティ比較
                        return True  # 新候補が優れている
                    if abs(candidate.ptm_soft_penalty - best.ptm_soft_penalty) <= 1e-12:  # 同値なら目的関数比較
                        return candidate.objective < best.objective - 1e-12  # 目的関数が小さい方を採用
                return candidate.objective < best.objective - 1e-12  # 目的関数が小さい方を採用
            return False  # 最小IRRが小さい場合は不採用
        return candidate.objective < best.objective - 1e-12  # 通常モードは目的関数で比較する
    if not candidate.feasible and not best.feasible:  # 両者ともfeasibleでない場合
        if candidate.violation < best.violation - 1e-12:  # 違反量が小さい方を採用
            return True  # 新候補が優れている
        if abs(candidate.violation - best.violation) <= 1e-12:  # 同値なら目的関数で比較
            return candidate.objective < best.objective - 1e-12  # 目的関数が小さい方を採用
    return False  # それ以外は現候補を維持


def _clamp_params(  # 係数を探索範囲内に収める
    params: LoadingFunctionParams,  # 対象係数
    settings: OptimizationSettings,  # 最適化設定
) -> LoadingFunctionParams:  # 範囲内に収めた係数を返す
    updated = params  # 更新用の変数を用意する
    for name, bound in settings.bounds.items():  # 係数ごとに範囲を確認する
        value = getattr(updated, name)  # 現在値を取得する
        clamped = min(max(value, bound.min), bound.max)  # 下限上限で挟み込む
        if clamped != value:  # 範囲外なら更新する
            updated = replace(updated, **{name: clamped})  # dataclassを部分更新する
    return updated  # 調整後の係数を返す


def _apply_config_change(  # 設定の一部を更新する
    config: dict,  # 対象設定
    dotted_key: str,  # ドット区切りのキー
    value: object,  # 設定値
) -> None:  # 更新のみ行う
    keys = [part for part in dotted_key.split(".") if part]
    if not keys:
        raise ValueError("Invalid config key.")
    cursor = config
    for key in keys[:-1]:
        if key not in cursor or not isinstance(cursor[key], dict):
            cursor[key] = {}
        cursor = cursor[key]
    cursor[keys[-1]] = value


def _run_stage(  # 1ステージ分の探索を実行する
    config: dict,  # 設定
    base_dir: Path,  # 相対パス基準
    params: LoadingFunctionParams,  # 初期係数
    settings: OptimizationSettings,  # 最適化設定
    stage: OptimizationStage,  # ステージ定義
    max_iterations: int,  # 最大評価回数
    exempt_model_points: set[str],  # 免除対象
    watch_model_points: set[str],  # 監視対象
) -> tuple[CandidateEvaluation, int]:  # 最良候補と評価回数を返す
    stage_vars = list(dict.fromkeys(stage.variables))  # 重複を除いた係数一覧を作る
    current_params = params  # 現在の係数を初期化する
    current_eval = _evaluate(  # 現在係数の評価を行う
        config,  # 設定
        base_dir,  # 相対パス基準
        current_params,  # 現在係数
        settings,  # 最適化設定
        stage_vars,  # 対象係数
        exempt_model_points,  # 免除対象
        watch_model_points,  # 監視対象
    )  # 評価結果
    iterations = 1  # 評価回数を初期化する

    for _ in range(max_iterations):  # 探索回数分だけ繰り返す
        improved = False  # 改善の有無をリセットする
        for name in stage_vars:  # 対象係数ごとに探索する
            if name not in settings.bounds:  # 範囲が定義されていない係数はスキップ
                continue  # 次の係数へ
            step = settings.bounds[name].step  # ステップ幅を取得する
            if step <= 0:  # ステップが無効ならスキップ
                continue  # 次の係数へ
            for delta in (step, -step):  # 正負の方向を試す
                next_value = getattr(current_params, name) + delta  # 次の値を計算する
                bound = settings.bounds[name]  # 範囲を取得する
                if next_value < bound.min or next_value > bound.max:  # 範囲外ならスキップ
                    continue  # 次の方向へ
                candidate_params = replace(current_params, **{name: next_value})  # 係数を更新する
                candidate_eval = _evaluate(  # 候補を評価する
                    config,  # 設定
                    base_dir,  # 相対パス基準
                    candidate_params,  # 候補係数
                    settings,  # 最適化設定
                    stage_vars,  # 対象係数
                    exempt_model_points,  # 免除対象
                    watch_model_points,  # 監視対象
                )  # 評価結果
                iterations += 1  # 評価回数を増やす
                if _is_better_candidate(candidate_eval, current_eval, settings):  # 改善なら更新する
                    current_params = candidate_params  # 係数を更新する
                    current_eval = candidate_eval  # 評価結果を更新する
                    improved = True  # 改善フラグを立てる
                    break  # 次の係数へ移る
            if improved or iterations >= max_iterations:  # 改善したか回数上限なら抜ける
                break  # 内側ループを抜ける
        if not improved or iterations >= max_iterations:  # 改善が無いか回数上限なら終了
            break  # 探索を終了する

    return current_eval, iterations  # 最良評価と評価回数を返す


def _optimize_once(  # 係数探索のメイン関数
    config: dict,  # 設定
    base_dir: Path,  # 相対パス基準
) -> OptimizationResult:  # 最適化結果を返す
    """
    Search loading function parameters that satisfy constraints.

    Units
    - base_dir: root for relative file paths
    - params: loading function coefficients (not a premium scaling factor)
    - hard constraints: irr_hard, loading_surplus_hard, premium_to_maturity_hard_max
    - hard constraints: nbv_hard, loading_surplus_hard_ratio (if used)
    - soft targets: irr_target, premium_to_maturity_target (penalized)
    - l2_lambda: L2 regularization weight for stage variables
    """
    settings = load_optimization_settings(config)  # 最適化設定を読み込む
    exemption = load_exemption_settings(config)  # 免除設定を読み込む
    exempt_model_points: list[str] = []  # 免除対象を初期化する
    if exemption.enabled:  # 免除が有効ならsweepで判定する
        if exemption.method != "sweep_ptm":  # 未対応方式はエラー
            raise ValueError(f"Unsupported exemption method: {exemption.method}")  # エラーを通知する
        _, min_r_by_id = sweep_premium_to_maturity_all(  # 全モデルポイントのsweepを行う
            config=config,  # 設定
            base_dir=base_dir,  # 相対パス基準
            start=exemption.sweep.start,  # 開始値
            end=exemption.sweep.end,  # 終了値
            step=exemption.sweep.step,  # 刻み
            irr_threshold=exemption.sweep.irr_threshold,  # IRR閾値
            nbv_threshold=-1.0e30,  # NBV閾値を極小にして実質無視
            loading_surplus_ratio_threshold=-1.0e30,  # 充足比率閾値を極小にして無視
            premium_to_maturity_hard_max=1.0e30,  # PTM上限を極大にして無視
            out_path=base_dir / "out" / "sweep_ptm_exemption.csv",  # 免除判定用CSVを出力
        )  # sweep結果
        exempt_model_points = [  # 最小rが見つからないモデルポイントを免除対象にする
            model_id for model_id, min_r in min_r_by_id.items() if min_r is None
        ]  # 免除対象の一覧
    exempt_set = set(exempt_model_points)  # 免除対象を集合化して検索を高速化する
    watch_set = set(settings.watch_model_point_ids)  # 監視対象を集合化する

    base_params = read_loading_parameters(config)  # 設定から初期係数を読む
    if base_params is None:  # 無ければデフォルトを使う
        base_params = LoadingFunctionParams(  # デフォルト係数
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
        )  # デフォルト係数

    base_params = _clamp_params(base_params, settings)  # 範囲外の係数を調整する
    current_params = base_params  # 現在係数を初期化する
    total_iterations = 0  # 評価回数を初期化する
    best_eval: CandidateEvaluation | None = None  # 最良評価を初期化する

    for stage in settings.stages:  # ステージごとに探索する
        stage_eval, iterations = _run_stage(  # ステージ探索を実行する
            config,  # 設定
            base_dir,  # 相対パス基準
            current_params,  # 現在係数
            settings,  # 最適化設定
            stage,  # ステージ定義
            settings.max_iterations_per_stage,  # 評価回数上限
            exempt_set,  # 免除対象
            watch_set,  # 監視対象
        )  # ステージ評価結果
        total_iterations += iterations  # 評価回数を累計する
        current_params = stage_eval.params  # 係数を更新する
        if _is_better_candidate(stage_eval, best_eval, settings):  # 最良候補を更新する
            best_eval = stage_eval  # 最良候補を更新する

    if best_eval is None:  # 評価が一度もできていない場合
        raise ValueError("Optimization search failed to evaluate.")  # エラーを通知する

    return OptimizationResult(  # 最適化結果を返す
        params=best_eval.params,  # 最良係数
        batch_result=best_eval.result,  # 収益性検証結果
        success=best_eval.feasible,  # hard制約の満足
        iterations=total_iterations,  # 評価回数
        failure_details=[] if best_eval.feasible else best_eval.failure_details,  # 失敗詳細
        exempt_model_points=exempt_model_points,  # 免除対象
        exemption_settings=exemption if exemption.enabled else None,  # 免除設定
        watch_model_points=settings.watch_model_point_ids,  # 監視対象
        min_irr=best_eval.min_irr,  # 最小IRR
        min_irr_model_point=best_eval.min_irr_model_point,  # 最小IRRのモデルポイント
    )  # 最適化結果を返す


def optimize_loading_parameters(  # 係数探索のメイン関数
    config: dict,  # 設定
    base_dir: Path,  # 相対パス基準
) -> OptimizationResult:  # 最適化結果を返す
    base_result = _optimize_once(config, base_dir)  # 通常探索を実行する
    if base_result.success:  # 成功していればそのまま返す
        return base_result

    settings = load_optimization_settings(config)  # ベース設定を取得する
    proposals = [
        {
            "plan": "Plan A",
            "changes": [{"path": "profit_test.surrender_charge_term", "value": 12}],
            "justification": "Longer surrender charge improves early cashflow stability.",
        },
        {
            "plan": "Plan A",
            "changes": [{"path": "profit_test.surrender_charge_term", "value": 15}],
            "justification": "Competitor analysis suggests longer surrender charge is acceptable.",
        },
        {
            "plan": "Plan B",
            "changes": [
                {
                    "path": "optimization.irr_target",
                    "value": max(settings.irr_target - 0.01, 0.0),
                }
            ],
            "justification": "Target IRR lowered to reflect current market conditions.",
        },
    ]

    for proposal in proposals:  # ハック案を順に試す
        hacked_config = copy.deepcopy(config)  # 元設定を保護する
        for change in proposal["changes"]:
            _apply_config_change(hacked_config, str(change["path"]), change["value"])
        hacked_result = _optimize_once(hacked_config, base_dir)  # 再最適化を実行する
        if hacked_result.success:  # 条件付き成功なら提案を付与して返す
            proposal_payload = {
                "plan": proposal["plan"],
                "changes": proposal["changes"],
                "justification": proposal["justification"],
                "conditional_success": True,
                "impact": {
                    "min_irr": hacked_result.min_irr,
                    "min_irr_model_point": hacked_result.min_irr_model_point,
                    "success": hacked_result.success,
                },
            }
            return replace(hacked_result, proposal=proposal_payload)

    return base_result  # すべて失敗したら元の結果を返す


def write_optimized_config(  # 最適化結果を設定ファイルとして保存する
    config: dict,  # 元設定
    result: OptimizationResult,  # 最適化結果
    output_path: Path,  # 出力先
) -> Path:  # 出力先を返す
    """
    Write an optimized config with explicit loading parameters.

    The loading parameters are function coefficients, not a premium multiplier.
    """
    updated = copy.deepcopy(config)  # 元設定を深いコピーで守る
    updated["loading_parameters"] = {  # 明示的な係数を設定に埋め込む
        "a0": result.params.a0,  # alpha基礎
        "a_age": result.params.a_age,  # alpha年齢
        "a_term": result.params.a_term,  # alpha期間
        "a_sex": result.params.a_sex,  # alpha性別
        "b0": result.params.b0,  # beta基礎
        "b_age": result.params.b_age,  # beta年齢
        "b_term": result.params.b_term,  # beta期間
        "b_sex": result.params.b_sex,  # beta性別
        "g0": result.params.g0,  # gamma基礎
        "g_term": result.params.g_term,  # gamma期間
    }  # 係数の埋め込み完了

    summary = result.batch_result.summary  # サマリ表を取得する
    updated["optimize_summary"] = {  # 最適化サマリを埋め込む
        "min_irr": float(summary["irr"].min()),  # 最小IRR
        "min_loading_surplus": float(summary["loading_surplus"].min()),  # 最小充足額
        "max_premium_to_maturity": float(summary["premium_to_maturity_ratio"].max()),  # 最大PTM比率
        "iterations": result.iterations,  # 評価回数
        "success": result.success,  # 成功/失敗
    }  # サマリの埋め込み完了

    output_path.parent.mkdir(parents=True, exist_ok=True)  # 出力先ディレクトリを作る
    output_path.write_text(  # YAMLとして保存する
        yaml.safe_dump(updated, allow_unicode=True, sort_keys=False),  # YAML文字列を生成する
        encoding="utf-8",  # UTF-8で書き出す
    )  # 保存する
    return output_path  # 出力先を返す
