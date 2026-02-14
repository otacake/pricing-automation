from __future__ import annotations  # 型注釈の前方参照を許可して循環参照を避けるため

"""
CLI entrypoint for pricing automation.
"""

import argparse  # CLI引数を扱うため
import copy  # 設定の深いコピーに使うため
import json  # JSON出力に使うため
from pathlib import Path  # パスをOSに依存せず扱うため

import yaml  # YAML設定を読み込むため

from .config import load_optimization_settings, loading_surplus_threshold, read_loading_parameters  # 設定値の解釈に使うため
from .diagnostics import build_execution_context, build_run_summary  # 構造化診断に使うため
from .optimize import optimize_loading_parameters, write_optimized_config  # 最適化の実行と結果保存に使うため
from .outputs import (  # 出力ファイル生成に使うため
    write_optimize_log,
    write_profit_test_excel,
    write_profit_test_log,
    write_run_summary_json,
)
from .paths import resolve_base_dir_from_config  # 相対パス解決の基準を決めるため
from .profit_test import run_profit_test  # 収益性検証の本体を呼び出すため
from .report_executive_pptx import report_executive_pptx_from_config  # 経営向けPPTXとMarkdownを生成するため
from .report_feasibility import report_feasibility_from_config  # Feasibility report generation
from .pdca_cycle import run_pdca_cycle
from .sweep_ptm import sweep_premium_to_maturity, sweep_premium_to_maturity_all  # premium-to-maturityのスイープ処理を呼ぶため


def _load_config(path: Path) -> dict:  # YAMLを読み込んで辞書に変換する補助関数
    return yaml.safe_load(path.read_text(encoding="utf-8"))  # ファイルをUTF-8で読み、YAMLを安全にパースする


def _parse_set_arguments(raw_values: list[str]) -> list[tuple[str, object]]:  # --set 引数を解析する
    updates: list[tuple[str, object]] = []
    for raw in raw_values:
        if "=" not in raw:
            raise SystemExit(f"Invalid --set value (expected key=value): {raw}")
        key, value_text = raw.split("=", 1)
        updates.append((key.strip(), yaml.safe_load(value_text)))
    return updates


def _apply_config_update(config: dict, dotted_key: str, value: object) -> object:  # 設定の一部を更新する
    keys = [part for part in dotted_key.split(".") if part]
    if not keys:
        raise SystemExit("Invalid key path for --set.")
    cursor = config
    for key in keys[:-1]:
        if key not in cursor or not isinstance(cursor[key], dict):
            cursor[key] = {}
        cursor = cursor[key]
    previous = cursor.get(keys[-1])
    cursor[keys[-1]] = value
    return previous


def _resolve_output_path(base_dir: Path, raw_path: str | Path | None, default: str) -> Path:
    path = Path(default) if raw_path is None else Path(raw_path)
    return path if path.is_absolute() else (base_dir / path)


def _format_run_output(config: dict, result) -> str:  # run結果を人が読みやすいテキストに整形する
    settings = load_optimization_settings(config)  # 最適化設定から制約値を取得する
    irr_min = settings.irr_hard  # IRRのハード下限を使う
    premium_hard_max = settings.premium_to_maturity_hard_max  # premium-to-maturity上限を使う
    nbv_hard = settings.nbv_hard  # NBVハード下限を使う
    watch_ids = set(settings.watch_model_point_ids)  # 監視対象を集合で保持して検索を高速化する

    loading_params = config.get("loading_parameters")  # 係数が明示されているか確認する
    if loading_params is None:  # 直接指定がなければ補助関数で読み取る
        params = read_loading_parameters(config)  # loading_parameters/ function から読み込む
        if params is not None:  # 読み取れた場合のみ辞書化する
            loading_params = {  # ログ出力用に辞書に詰める
                "a0": params.a0,  # alpha基礎
                "a_age": params.a_age,  # alpha年齢
                "a_term": params.a_term,  # alpha期間
                "a_sex": params.a_sex,  # alpha性別
                "b0": params.b0,  # beta基礎
                "b_age": params.b_age,  # beta年齢
                "b_term": params.b_term,  # beta期間
                "b_sex": params.b_sex,  # beta性別
                "g0": params.g0,  # gamma基礎
                "g_term": params.g_term,  # gamma期間
            }  # 辞書化したパラメータ

    lines = ["run"]  # 出力行を配列で構築する
    if loading_params:  # loading係数があれば出力に含める
        lines.append("loading_parameters")  # セクション見出しを追加する
        for key in [  # 表示順を固定するためのキー配列
            "a0",  # alpha基礎
            "a_age",  # alpha年齢
            "a_term",  # alpha期間
            "a_sex",  # alpha性別
            "b0",  # beta基礎
            "b_age",  # beta年齢
            "b_term",  # beta期間
            "b_sex",  # beta性別
            "g0",  # gamma基礎
            "g_term",  # gamma期間
        ]:  # 出力順の定義ここまで
            if key in loading_params:  # キーが存在する場合のみ出力する
                lines.append(f"{key}: {loading_params[key]}")  # 値を文字列化して追加する

    lines.append("model_point_results")  # モデルポイント結果のセクションを開始する
    for row in result.summary.itertuples(index=False):  # サマリ行を走査して出力する
        threshold = loading_surplus_threshold(settings, int(row.sum_assured))  # 充足額の閾値を算出する
        loading_ratio = row.loading_surplus / float(row.sum_assured)  # 充足比率を計算する
        irr_ok = row.irr >= irr_min  # IRR制約を満たすか判定する
        loading_ok = row.loading_surplus >= threshold  # 充足額制約を満たすか判定する
        premium_ok = row.premium_to_maturity_ratio <= premium_hard_max  # premium-to-maturity上限制約を判定する
        nbv_ok = row.new_business_value >= nbv_hard  # NBV制約を判定する
        if row.model_point in watch_ids:  # 監視対象ならステータスを特別扱いする
            status = "watch"  # 監視ステータス
        else:  # 監視対象でなければ通常判定
            status = "pass" if irr_ok and loading_ok and premium_ok and nbv_ok else "fail"  # 全制約を満たすかで判定する
        lines.append(  # 1行で主要な指標を出力する
            f"{row.model_point} irr={row.irr} nbv={row.new_business_value} "  # IRRとNBVを出力する
            f"loading_surplus={row.loading_surplus} premium_to_maturity={row.premium_to_maturity_ratio} "  # 充足額とPTMを出力する
            f"loading_surplus_threshold={threshold} loading_surplus_ratio={loading_ratio} "  # 閾値と比率を出力する
            f"status={status}"  # ステータスを出力する
        )  # 行を追加する
        if status == "fail":  # 失敗の場合は短所を追記する
            if not irr_ok:  # IRRが下限未達の場合
                lines.append(  # shortfall情報を出力する
                    f"shortfall: irr_hard {row.model_point} {irr_min - row.irr:.6f}"
                )  # IRR不足分を出力する
            if not loading_ok:  # 充足額が不足する場合
                lines.append(  # shortfall情報を出力する
                    f"shortfall: loading_surplus_hard {row.model_point} {threshold - row.loading_surplus:.2f}"
                )  # 充足額不足分を出力する
            if not premium_ok:  # premium-to-maturityが上限超過の場合
                lines.append(  # shortfall情報を出力する
                    f"shortfall: premium_to_maturity_hard {row.model_point} {row.premium_to_maturity_ratio - premium_hard_max:.6f}"
                )  # 超過分を出力する
            if not nbv_ok:  # NBVが下限未達の場合
                lines.append(  # shortfall情報を出力する
                    f"shortfall: nbv_hard {row.model_point} {nbv_hard - row.new_business_value:.2f}"
                )  # 不足分を出力する
        if row.premium_to_maturity_ratio > premium_hard_max:  # PTM上限を超える場合のみ警告する
            lines.append(f"warning: premium_total_exceeds_hard_max {row.model_point}")  # 警告を出力する

    if any(  # IRR制約が1つでも破れているか判定する
        row.irr < irr_min and row.model_point not in watch_ids  # 監視対象を除いて判定する
        for row in result.summary.itertuples(index=False)  # サマリ行を走査する
    ):  # 判定条件ここまで
        lines.append("constraint_check: irr_hard failed")  # 制約違反のまとめを出す
    if any(  # 充足額制約が破れているか判定する
        row.loading_surplus < loading_surplus_threshold(settings, int(row.sum_assured))  # 閾値を計算して判定
        and row.model_point not in watch_ids  # 監視対象は除外する
        for row in result.summary.itertuples(index=False)  # サマリ行を走査する
    ):  # 判定条件ここまで
        lines.append("constraint_check: loading_surplus_hard failed")  # 制約違反のまとめを出す
    if any(  # premium-to-maturity制約が破れているか判定する
        row.premium_to_maturity_ratio > premium_hard_max  # 上限超過を判定する
        and row.model_point not in watch_ids  # 監視対象は除外する
        for row in result.summary.itertuples(index=False)  # サマリ行を走査する
    ):  # 判定条件ここまで
        lines.append("constraint_check: premium_to_maturity_hard failed")  # 制約違反のまとめを出す
    if any(  # NBV制約が破れているか判定する
        row.new_business_value < nbv_hard and row.model_point not in watch_ids  # 監視対象を除外して判定する
        for row in result.summary.itertuples(index=False)  # サマリ行を走査する
    ):  # 判定条件ここまで
        lines.append("constraint_check: nbv_hard failed")  # 制約違反のまとめを出す

    return "\n".join(lines)  # まとめた行を1つの文字列として返す


def run_from_config(config_path: Path) -> int:  # YAML設定を使ってprofit testを実行する
    """
    Run profit test from a YAML config file and write outputs.
    """
    config_path = config_path.expanduser().resolve()
    config = _load_config(config_path)  # 設定ファイルを読み込む
    base_dir = resolve_base_dir_from_config(config_path)  # 相対パス解決の基準ディレクトリを取得する
    result = run_profit_test(config, base_dir=base_dir)  # 収益性検証を実行する

    outputs_cfg = config.get("outputs", {})  # 出力設定を取得する
    excel_path = _resolve_output_path(base_dir, outputs_cfg.get("excel_path"), "out/result.xlsx")
    log_path = _resolve_output_path(base_dir, outputs_cfg.get("log_path"), "out/result.log")

    write_profit_test_excel(excel_path, result)  # Excel結果を書き出す
    write_profit_test_log(log_path, config, result)  # ログ結果を書き出す
    summary_path = _resolve_output_path(base_dir, outputs_cfg.get("run_summary_path"), "out/run_summary.json")
    execution_context = build_execution_context(
        config=config,
        base_dir=base_dir,
        config_path=config_path,
        command="pricing.cli run",
        argv=[str(config_path)],
    )
    write_run_summary_json(
        summary_path,
        config,
        result,
        source="run",
        execution_context=execution_context,
    )
    print(_format_run_output(config, result))  # 標準出力にも結果サマリを表示する
    return 0  # 正常終了コードを返す


def optimize_from_config(config_path: Path) -> int:  # YAML設定を使って最適化を実行する
    """
    Optimize loading parameters from a YAML config file.
    """
    config_path = config_path.expanduser().resolve()
    config = _load_config(config_path)  # 設定ファイルを読み込む
    base_dir = resolve_base_dir_from_config(config_path)  # 相対パス解決の基準ディレクトリを取得する
    result = optimize_loading_parameters(config, base_dir=base_dir)  # 最適化を実行する

    outputs_cfg = config.get("outputs", {})  # 出力設定を取得する
    log_path = _resolve_output_path(base_dir, outputs_cfg.get("log_path"), "out/result.log")
    write_optimize_log(log_path, config, result)  # 最適化ログを出力する

    optimized_path = outputs_cfg.get("optimized_config_path")  # 最適化後の設定保存先を取得する
    if optimized_path:  # 設定に保存先があればそれを使う
        output_path = base_dir / optimized_path  # 相対パスを基準ディレクトリに結合する
    else:  # 明示が無ければ元ファイル名に .optimized を付ける
        output_path = config_path.with_name(f"{config_path.stem}.optimized.yaml")  # デフォルトの保存先を作る
    write_optimized_config(config, result, output_path)  # 最適化後の設定ファイルを書き出す

    print(log_path.read_text(encoding="utf-8"))  # ログ内容を標準出力に表示する
    return 0  # 正常終了コードを返す


def propose_change_from_config(  # 変更案を評価する
    config_path: Path,  # 設定ファイルのパス
    updates: list[tuple[str, object]],  # 変更内容
    reason: str,  # 変更理由
    out_path: Path | None,  # 出力パス（任意）
) -> int:
    config_path = config_path.expanduser().resolve()
    config = _load_config(config_path)  # 設定ファイルを読み込む
    base_dir = resolve_base_dir_from_config(config_path)  # 相対パス解決の基準ディレクトリを取得する
    execution_context = build_execution_context(
        config=config,
        base_dir=base_dir,
        config_path=config_path,
        command="pricing.cli propose-change",
        argv=[str(config_path)],
    )
    baseline_result = run_profit_test(config, base_dir=base_dir)  # 変更前の結果を計算する
    baseline_summary = build_run_summary(
        config,
        baseline_result,
        source="propose_change_baseline",
        execution_context=execution_context,
    )

    updated_config = copy.deepcopy(config)  # 変更用に深いコピーを作る
    changes: list[dict[str, object]] = []
    for key, value in updates:
        previous = _apply_config_update(updated_config, key, value)
        changes.append({"path": key, "before": previous, "after": value})

    proposal_result = run_profit_test(updated_config, base_dir=base_dir)  # 変更後の結果を計算する
    proposal_summary = build_run_summary(
        updated_config,
        proposal_result,
        source="propose_change_candidate",
        execution_context=execution_context,
    )

    def _metrics(summary: dict) -> dict[str, float]:
        data = summary["summary"]
        return {
            "min_irr": float(data["min_irr"]),
            "min_nbv": float(data["min_nbv"]),
            "min_loading_surplus_ratio": float(data["min_loading_surplus_ratio"]),
            "max_premium_to_maturity": float(data["max_premium_to_maturity"]),
            "violation_count": float(data["violation_count"]),
        }

    base_metrics = _metrics(baseline_summary)
    proposal_metrics = _metrics(proposal_summary)
    delta = {key: proposal_metrics[key] - base_metrics[key] for key in base_metrics}

    base_status = {mp["model_point"]: mp["status"] for mp in baseline_summary["model_points"]}
    proposal_status = {mp["model_point"]: mp["status"] for mp in proposal_summary["model_points"]}
    affected = sorted(
        mp for mp in proposal_status if proposal_status.get(mp) != base_status.get(mp)
    )

    output = {
        "meta": {"reason": reason, "config_path": str(config_path)},
        "changes": changes,
        "baseline": baseline_summary,
        "proposal": proposal_summary,
        "delta": delta,
        "affected_model_points": affected,
    }

    output_path = _resolve_output_path(base_dir, out_path, "out/propose_change.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=True), encoding="utf-8")

    print("propose_change")
    print(f"reason: {reason}")
    for change in changes:
        print(f"change: {change['path']} {change['before']} -> {change['after']}")
    print(f"baseline: {base_metrics}")
    print(f"proposal: {proposal_metrics}")
    print(f"delta: {delta}")
    if affected:
        print("affected_model_points:")
        for mp in affected:
            print(f"- {mp} {base_status.get(mp)} -> {proposal_status.get(mp)}")
    print(f"wrote: {output_path}")
    return 0


def sweep_ptm_from_config(  # premium-to-maturityスイープをYAML設定から実行する
    config_path: Path,  # 設定ファイルのパス
    model_point_label: str,  # 対象モデルポイントのラベル
    start: float,  # スイープ開始値
    end: float,  # スイープ終了値
    step: float,  # スイープ刻み
    irr_threshold: float,  # IRR閾値
    nbv_threshold: float,  # NBV閾値
    loading_surplus_ratio_threshold: float,  # 費用充足比率の閾値
    premium_to_maturity_hard_max: float,  # premium-to-maturityの上限
    out_path: Path | None,  # 出力ファイルの指定（任意）
    all_model_points: bool,  # 全モデルポイント対象かどうか
) -> int:  # 正常終了コードを返す
    """
    Sweep premium-to-maturity ratios for model points and write CSV output.
    """
    config_path = config_path.expanduser().resolve()
    config = _load_config(config_path)  # 設定ファイルを読み込む
    base_dir = resolve_base_dir_from_config(config_path)  # 相対パス解決の基準ディレクトリを取得する
    output_path = out_path  # 出力先を一旦受け取る
    if output_path is None:  # 出力先指定がない場合はデフォルトを使う
        output_path = (  # 全件か単独かで出力名を切り替える
            base_dir / "out/sweep_ptm_all.csv"  # 全件スイープ時の出力名
            if all_model_points  # 全件かどうかの判定
            else base_dir / f"out/sweep_ptm_{model_point_label}.csv"  # 単独スイープ時の出力名
        )  # 出力先の決定ここまで
    else:
        output_path = _resolve_output_path(base_dir, output_path, "out/sweep_ptm.csv")

    if all_model_points:  # 全モデルポイントを対象とする場合
        try:  # 例外を捕捉してCLIの終了コードに変換する
            _, min_r_by_id = sweep_premium_to_maturity_all(  # 全件スイープを実行する
                config=config,  # 設定を渡す
                base_dir=base_dir,  # 基準ディレクトリを渡す
                start=start,  # 開始値
                end=end,  # 終了値
                step=step,  # 刻み
                irr_threshold=irr_threshold,  # IRR閾値
                nbv_threshold=nbv_threshold,  # NBV閾値
                loading_surplus_ratio_threshold=loading_surplus_ratio_threshold,  # 充足比率閾値
                premium_to_maturity_hard_max=premium_to_maturity_hard_max,  # PTM上限
                out_path=output_path,  # CSV出力先
            )  # スイープ実行
        except ValueError as exc:  # 入力不正などの例外
            raise SystemExit(2) from exc  # CLIとしてエラー終了に変換する

        print("min_r_by_model_point")  # 最小rの結果を出力する見出し
        for model_id, min_r in min_r_by_id.items():  # 各モデルポイントの最小rを表示する
            if min_r is None:  # 見つからない場合
                print(f"{model_id}: not found")  # 見つからない旨を出力
            else:  # 見つかった場合
                print(f"{model_id}: {min_r}")  # 最小rを出力
    else:  # 単独モデルポイントの場合
        try:  # 例外を捕捉してCLIの終了コードに変換する
            df, min_r = sweep_premium_to_maturity(  # 単独スイープを実行する
                config=config,  # 設定を渡す
                base_dir=base_dir,  # 基準ディレクトリを渡す
                model_point_label=model_point_label,  # 対象モデルポイントを指定する
                start=start,  # 開始値
                end=end,  # 終了値
                step=step,  # 刻み
                irr_threshold=irr_threshold,  # IRR閾値
                out_path=output_path,  # CSV出力先
            )  # スイープ実行
        except ValueError as exc:  # 入力不正などの例外
            raise SystemExit(2) from exc  # CLIとしてエラー終了に変換する

        print(df.to_csv(index=False))  # 結果CSVを標準出力に表示する
        if min_r is None:  # 見つからない場合
            print("min_r: not found")  # 見つからない旨を出力する
        else:  # 見つかった場合
            print(f"min_r: {min_r}")  # 最小rを出力する
    return 0  # 正常終了コードを返す


def main(argv: list[str] | None = None) -> int:  # CLIのメイン処理を実装する
    parser = argparse.ArgumentParser(description="Pricing automation CLI.")  # CLI全体の説明を設定する
    subparsers = parser.add_subparsers(dest="command", required=True)  # サブコマンドを必須化する

    run_parser = subparsers.add_parser("run", help="Run profit test with a config.")  # runコマンドを定義する
    run_parser.add_argument("config", type=str, help="Path to config YAML.")  # 設定ファイルを引数で受け取る
    optimize_parser = subparsers.add_parser(  # optimizeコマンドを定義する
        "optimize", help="Optimize loading parameters with a config."
    )  # optimizeコマンドの登録
    optimize_parser.add_argument("config", type=str, help="Path to config YAML.")  # 設定ファイルを引数で受け取る
    sweep_parser = subparsers.add_parser(  # sweep-ptmコマンドを定義する
        "sweep-ptm", help="Sweep premium-to-maturity ratios for a model point."
    )  # sweep-ptmコマンドの登録
    sweep_parser.add_argument("config", type=str, help="Path to config YAML.")  # 設定ファイルを引数で受け取る
    sweep_parser.add_argument(  # モデルポイントの指定を追加する
        "--model-point",  # 引数名
        type=str,  # 文字列として受け取る
        default="male_age30_term35",  # デフォルトのモデルポイント
        help="Target model point label.",  # 引数の説明
    )  # 引数定義
    sweep_parser.add_argument("--start", type=float, required=True)  # スイープ開始値
    sweep_parser.add_argument("--end", type=float, required=True)  # スイープ終了値
    sweep_parser.add_argument("--step", type=float, required=True)  # スイープ刻み
    sweep_parser.add_argument("--irr-threshold", type=float, default=0.04)  # IRR閾値
    sweep_parser.add_argument("--all-model-points", action="store_true")  # 全モデルポイント対象フラグ
    sweep_parser.add_argument(  # 充足比率の閾値を指定する
        "--loading-surplus-ratio-threshold", type=float, default=-0.10
    )  # 引数定義
    sweep_parser.add_argument("--nbv-threshold", type=float, default=0.0)  # NBV閾値
    sweep_parser.add_argument("--premium-to-maturity-hard-max", type=float, default=1.05)  # PTM上限
    sweep_parser.add_argument("--out", type=str, default=None)  # 出力先の指定

    report_parser = subparsers.add_parser(
        "report-feasibility", help="Generate feasibility report deck."
    )
    report_parser.add_argument("config", type=str, help="Path to config YAML.")
    report_parser.add_argument("--r-start", type=float, default=1.0)
    report_parser.add_argument("--r-end", type=float, default=1.05)
    report_parser.add_argument("--r-step", type=float, default=0.01)
    report_parser.add_argument("--irr-threshold", type=float, default=0.04)
    report_parser.add_argument("--out", type=str, default="out/feasibility_deck.yaml")

    executive_parser = subparsers.add_parser(
        "report-executive-pptx",
        help="Generate executive PPTX and Markdown deliverables.",
    )
    executive_parser.add_argument("config", type=str, help="Path to config YAML.")
    executive_parser.add_argument("--out", type=str, default="reports/executive_pricing_deck.pptx")
    executive_parser.add_argument("--md-out", type=str, default="reports/feasibility_report.md")
    executive_parser.add_argument(
        "--run-summary-out", type=str, default="out/run_summary_executive.json"
    )
    executive_parser.add_argument(
        "--deck-out", type=str, default="out/feasibility_deck_executive.yaml"
    )
    executive_parser.add_argument("--chart-dir", type=str, default="out/charts/executive")
    executive_parser.add_argument("--r-start", type=float, default=1.0)
    executive_parser.add_argument("--r-end", type=float, default=1.08)
    executive_parser.add_argument("--r-step", type=float, default=0.005)
    executive_parser.add_argument("--irr-threshold", type=float, default=0.02)
    executive_parser.add_argument(
        "--lang",
        type=str,
        choices=("ja", "en"),
        default="ja",
        help="Language for Markdown/PPTX deliverables.",
    )
    executive_parser.add_argument(
        "--chart-lang",
        type=str,
        choices=("ja", "en"),
        default="en",
        help="Language for chart text. Default is English to avoid font issues.",
    )

    cycle_parser = subparsers.add_parser(
        "run-cycle",
        help="Run autonomous PDCA pricing cycle with policy.",
    )
    cycle_parser.add_argument("config", type=str, help="Path to config YAML.")
    cycle_parser.add_argument(
        "--policy",
        type=str,
        default="policy/pricing_policy.yaml",
        help="Path to auto cycle policy YAML.",
    )
    cycle_parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip pytest pre-check in cycle.",
    )

    propose_parser = subparsers.add_parser(
        "propose-change", help="Evaluate a parameter change without persisting it."
    )
    propose_parser.add_argument("config", type=str, help="Path to config YAML.")
    propose_parser.add_argument(
        "--set",
        dest="set_values",
        action="append",
        default=[],
        help="Set a config value (e.g., loading_parameters.a_age=0.002).",
    )
    propose_parser.add_argument("--reason", type=str, required=True)
    propose_parser.add_argument("--out", type=str, default="out/propose_change.json")
    args = parser.parse_args(argv)  # CLI引数を解析する
    if args.command == "run":  # runコマンドの場合
        return run_from_config(Path(args.config))  # run処理を実行する
    if args.command == "optimize":  # optimizeコマンドの場合
        return optimize_from_config(Path(args.config))  # 最適化処理を実行する
    if args.command == "sweep-ptm":  # sweep-ptmコマンドの場合
        return sweep_ptm_from_config(  # スイープ処理を実行する
            Path(args.config),  # 設定ファイルのパス
            model_point_label=args.model_point,  # モデルポイントラベル
            start=float(args.start),  # 開始値
            end=float(args.end),  # 終了値
            step=float(args.step),  # 刻み
            irr_threshold=float(args.irr_threshold),  # IRR閾値
            nbv_threshold=float(args.nbv_threshold),  # NBV閾値
            loading_surplus_ratio_threshold=float(args.loading_surplus_ratio_threshold),  # 充足比率閾値
            premium_to_maturity_hard_max=float(args.premium_to_maturity_hard_max),  # PTM上限
            out_path=Path(args.out) if args.out else None,  # 出力先（指定時のみ）
            all_model_points=bool(args.all_model_points),  # 全モデルポイントフラグ
        )  # sweep-ptmを実行する

    if args.command == "report-feasibility":  # report-feasibility command
        output_path = report_feasibility_from_config(
            Path(args.config),
            r_start=float(args.r_start),
            r_end=float(args.r_end),
            r_step=float(args.r_step),
            irr_threshold=float(args.irr_threshold),
            out_path=Path(args.out),
        )
        print(f"wrote: {output_path}")
        return 0
    if args.command == "report-executive-pptx":
        outputs = report_executive_pptx_from_config(
            Path(args.config),
            out_path=Path(args.out),
            markdown_path=Path(args.md_out),
            run_summary_path=Path(args.run_summary_out),
            deck_out_path=Path(args.deck_out),
            chart_dir=Path(args.chart_dir),
            r_start=float(args.r_start),
            r_end=float(args.r_end),
            r_step=float(args.r_step),
            irr_threshold=float(args.irr_threshold),
            language=str(args.lang),
            chart_language=str(args.chart_lang),
        )
        print(f"wrote_pptx: {outputs.pptx_path}")
        print(f"wrote_markdown: {outputs.markdown_path}")
        print(f"wrote_run_summary: {outputs.run_summary_path}")
        print(f"wrote_feasibility_deck: {outputs.feasibility_deck_path}")
        print(f"wrote_cashflow_chart: {outputs.cashflow_chart_path}")
        print(f"wrote_premium_chart: {outputs.premium_chart_path}")
        return 0
    if args.command == "run-cycle":
        outputs = run_pdca_cycle(
            Path(args.config),
            policy_path=Path(args.policy),
            skip_tests=bool(args.skip_tests),
        )
        print(f"run_id: {outputs.run_id}")
        print(f"wrote_manifest: {outputs.manifest_path}")
        print(f"wrote_baseline_summary: {outputs.baseline_summary_path}")
        print(f"wrote_final_summary: {outputs.final_summary_path}")
        print(f"wrote_result_log: {outputs.result_log_path}")
        print(f"wrote_result_excel: {outputs.result_excel_path}")
        if outputs.optimized_config_path is not None:
            print(f"wrote_optimized_config: {outputs.optimized_config_path}")
        if outputs.feasibility_deck_path is not None:
            print(f"wrote_feasibility_deck: {outputs.feasibility_deck_path}")
        if outputs.markdown_report_path is not None:
            print(f"wrote_markdown: {outputs.markdown_report_path}")
        if outputs.executive_pptx_path is not None:
            print(f"wrote_pptx: {outputs.executive_pptx_path}")
        return 0
    if args.command == "propose-change":
        if not args.set_values:
            raise SystemExit("propose-change requires at least one --set value.")
        updates = _parse_set_arguments(args.set_values)
        return propose_change_from_config(
            Path(args.config),
            updates=updates,
            reason=str(args.reason),
            out_path=Path(args.out) if args.out else None,
        )
    return 1  # 未知のコマンドは異常終了として扱う


if __name__ == "__main__":  # 直接実行された場合のみCLIを起動する
    raise SystemExit(main())  # mainの戻り値を終了コードとして返す
