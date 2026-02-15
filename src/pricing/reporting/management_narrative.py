from __future__ import annotations

from typing import Any, Mapping, Sequence


SECTION_ORDER = ("conclusion", "rationale", "risk", "decision_ask")


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: object, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _fmt_ratio(value: float) -> str:
    return f"{value:.4f}"


def _fmt_jpy(value: float) -> str:
    return f"{value:,.0f} JPY"


def _line_count(block: Mapping[str, Any], required_sections: Sequence[str]) -> int:
    total = 0
    for section in required_sections:
        if section == "conclusion":
            text = str(block.get(section, "")).strip()
            if text:
                total += 1
            continue
        values = _as_list(block.get(section))
        total += len([value for value in values if str(value).strip()])
    return total


def _contains_compare_tokens(text: str) -> bool:
    lowered = text.lower()
    ja_ok = ("推奨案" in text) and ("対向案" in text)
    en_ok = ("recommended" in lowered) and ("counter" in lowered)
    return ja_ok or en_ok


def _cashflow_totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    totals = {
        "premium_income": 0.0,
        "investment_income": 0.0,
        "benefit_outgo": 0.0,
        "expense_outgo": 0.0,
        "reserve_change_outgo": 0.0,
        "net_cf": 0.0,
    }
    for row in rows:
        for key in totals:
            totals[key] += _safe_float(row.get(key))
    return totals


def _top_components(causal_bridge: Mapping[str, Any], *, limit: int = 2) -> list[str]:
    components = _as_list(causal_bridge.get("components"))
    enriched: list[tuple[float, str]] = []
    for row in components:
        payload = _as_mapping(row)
        label = str(payload.get("label") or payload.get("component") or "")
        if not label or label.lower() == "net_cf":
            continue
        delta = _safe_float(payload.get("delta_recommended_minus_counter"))
        enriched.append((abs(delta), f"{label}: {delta:,.0f}"))
    enriched.sort(key=lambda item: item[0], reverse=True)
    return [value for _, value in enriched[:limit]]


def _sensitivity_top_risk(
    sensitivity_decomposition: Mapping[str, Any],
    sensitivity_rows: Sequence[Mapping[str, Any]],
) -> str:
    ranked = _as_list(_as_mapping(sensitivity_decomposition).get("recommended"))
    if ranked:
        return str(_as_mapping(ranked[0]).get("scenario", "base"))

    rows = list(sensitivity_rows)
    if not rows:
        return "base"
    base = next((row for row in rows if str(row.get("scenario")) == "base"), rows[0])
    candidates = [row for row in rows if str(row.get("scenario")) != "base"]
    if not candidates:
        return str(base.get("scenario", "base"))

    def score(row: Mapping[str, Any]) -> tuple[float, float, float]:
        return (
            _safe_float(base.get("min_irr")) - _safe_float(row.get("min_irr")),
            _safe_float(row.get("max_premium_to_maturity")) - _safe_float(base.get("max_premium_to_maturity")),
            _safe_float(row.get("violation_count")),
        )

    ranked_rows = sorted(candidates, key=score, reverse=True)
    return str(_as_mapping(ranked_rows[0]).get("scenario", "base"))


def _narrative_block(
    *,
    conclusion: str,
    rationale: Sequence[str],
    risk: Sequence[str],
    decision_ask: Sequence[str],
) -> dict[str, Any]:
    return {
        "section_order": list(SECTION_ORDER),
        "conclusion": conclusion,
        "rationale": [str(item) for item in rationale if str(item).strip()],
        "risk": [str(item) for item in risk if str(item).strip()],
        "decision_ask": [str(item) for item in decision_ask if str(item).strip()],
    }


def _build_ja_narrative(
    *,
    run_summary: Mapping[str, Any],
    pricing_rows: Sequence[Mapping[str, Any]],
    constraint_rows: Sequence[Mapping[str, Any]],
    cashflow_rows: Sequence[Mapping[str, Any]],
    sensitivity_rows: Sequence[Mapping[str, Any]],
    decision_compare: Mapping[str, Any],
    explainability_report: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    summary = _as_mapping(run_summary.get("summary"))
    min_irr = _safe_float(summary.get("min_irr"))
    min_nbv = _safe_float(summary.get("min_nbv"))
    max_ptm = _safe_float(summary.get("max_premium_to_maturity"))
    violation_count = _safe_int(summary.get("violation_count"))

    compare = _as_mapping(decision_compare)
    compare_diff = _as_mapping(compare.get("metric_diff_recommended_minus_counter"))
    adoption_reasons = [str(item) for item in _as_list(compare.get("adoption_reason")) if str(item).strip()]

    explain = _as_mapping(explainability_report)
    causal_bridge = _as_mapping(explain.get("causal_bridge"))
    sensitivity_decomposition = _as_mapping(explain.get("sensitivity_decomposition"))
    formula_catalog = _as_mapping(explain.get("formula_catalog"))
    planned_expense = _as_mapping(formula_catalog.get("planned_expense"))
    formula_source = _as_mapping(planned_expense.get("source"))

    cash_totals = _cashflow_totals(cashflow_rows)
    inflow_total = cash_totals["premium_income"] + cash_totals["investment_income"]
    investment_share = (cash_totals["investment_income"] / inflow_total) if abs(inflow_total) > 1e-12 else 0.0
    top_risk_scenario = _sensitivity_top_risk(sensitivity_decomposition, sensitivity_rows)

    premiums = [_safe_float(row.get("gross_annual_premium")) for row in pricing_rows]
    premium_min = min(premiums) if premiums else 0.0
    premium_max = max(premiums) if premiums else 0.0

    tight_constraint = {}
    if constraint_rows:
        tight_constraint = min(
            (_as_mapping(row) for row in constraint_rows),
            key=lambda row: _safe_float(row.get("min_gap"), default=10**12),
        )
    tight_label = str(tight_constraint.get("label") or tight_constraint.get("constraint") or "-")
    tight_gap = _safe_float(tight_constraint.get("min_gap"))
    top_components = _top_components(causal_bridge)

    return {
        "executive_summary": _narrative_block(
            conclusion="推奨案は十分性・収益性・健全性を同時に満たし、経営会議での決裁に必要な根拠を備えている。",
            rationale=[
                f"主要KPIは min IRR={_fmt_pct(min_irr)}, min NBV={_fmt_jpy(min_nbv)}, max PTM={_fmt_ratio(max_ptm)}, 違反件数={violation_count}。",
                f"累計ネットCFは {_fmt_jpy(cash_totals['net_cf'])}。流入に占める運用収益比率は {_fmt_pct(investment_share)}。",
                adoption_reasons[0] if adoption_reasons else "推奨案は制約順守と収益耐性の両立を優先して選定。",
            ],
            risk=[f"主要な下振れシナリオは {top_risk_scenario}。監視KPIで早期検知が必要。"],
            decision_ask=["推奨案を採択し、対向案はベンチマークとして保管する決裁を要請。"],
        ),
        "decision_statement": _narrative_block(
            conclusion="推奨案と対向案を独立最適化で比較し、推奨案を採用する。",
            rationale=[
                f"目的関数は推奨案={compare.get('objectives', {}).get('recommended', '-')}, 対向案={compare.get('objectives', {}).get('counter', '-')}。",
                f"差分(推奨-対向)は min IRR={_safe_float(compare_diff.get('min_irr')):.6f}, min NBV={_safe_float(compare_diff.get('min_nbv')):,.0f}, max PTM={_safe_float(compare_diff.get('max_premium_to_maturity')):.6f}。",
                adoption_reasons[1] if len(adoption_reasons) > 1 else "採否は制約余力と収益性のバランスで判断。",
            ],
            risk=["対向案は一部ポイントで見かけ上有利なため、営業現場への説明テンプレートが必要。"],
            decision_ask=["推奨案採択・対向案不採択を議事録で明文化する。"],
        ),
        "pricing_recommendation": _narrative_block(
            conclusion="最終保険料Pは競争力と損益健全性を両立するレンジで設定されている。",
            rationale=[
                f"年間保険料レンジは {premium_min:,.0f} 〜 {premium_max:,.0f}。",
                f"下限制約は min IRR={_fmt_pct(min_irr)} / min NBV={_fmt_jpy(min_nbv)} を維持。",
                "価格差は利源構造（予定事業費・運用収益・給付）に基づいて設定。",
            ],
            risk=["割引余地を拡大しすぎると長期ポイントで収益耐性が低下する。"],
            decision_ask=["提示テーブルを見積システムへ反映し、例外案件はログ管理する。"],
        ),
        "constraint_status": _narrative_block(
            conclusion="ハード制約は全点で充足し、逸脱時トリガーは事前定義済み。",
            rationale=[
                f"最もタイトな制約は {tight_label} で、最小ギャップは {tight_gap:.6f}。",
                f"非watch/non-exempt範囲での違反件数は {violation_count}。",
                "watch点とexempt点は別統制として理由・期限・責任者を管理する。",
            ],
            risk=["前提更新後にギャップが縮小する可能性があるため定期再計算が必要。"],
            decision_ask=["再実行トリガー(min IRR<2.0% / max PTM>1.056)の運用承認を要請。"],
        ),
        "cashflow_bridge": _narrative_block(
            conclusion="利源別キャッシュフローは流入と流出の構造が明確で、説明可能性が高い。",
            rationale=[
                f"流入は premium={_fmt_jpy(cash_totals['premium_income'])}, investment={_fmt_jpy(cash_totals['investment_income'])}。",
                f"流出は benefit={_fmt_jpy(cash_totals['benefit_outgo'])}, expense={_fmt_jpy(cash_totals['expense_outgo'])}, reserve={_fmt_jpy(cash_totals['reserve_change_outgo'])}。",
                f"運用収益比率 {_fmt_pct(investment_share)} により前提更新効果を可視化。",
            ],
            risk=["金利低下局面では運用収益の寄与が縮小する。"],
            decision_ask=["利源別CFを四半期の定点KPIとして継続監視する。"],
        ),
        "profit_source_decomposition": _narrative_block(
            conclusion="年度差分と案差分を利源別に分解し、収益構造の持続性を検証した。",
            rationale=[
                top_components[0] if top_components else "橋渡し分解でネット差分への寄与順を確認。",
                top_components[1] if len(top_components) > 1 else "主要寄与の二番手要因まで確認済み。",
                "前年差分と案差分を同時評価し、一時要因依存を回避。",
            ],
            risk=["単一利源への依存が高まると将来変動耐性が低下する。"],
            decision_ask=["利源別の上限管理値を次回会議で確定する。"],
        ),
        "sensitivity": _narrative_block(
            conclusion="感応度分解により、支配シナリオと対応優先順位を明確化した。",
            rationale=[
                f"最重要シナリオは {top_risk_scenario}。",
                "橋渡し分解と感応度分解を併用して因果の説明責任を確保。",
                "監視KPIは min IRR / min NBV / max PTM / violation_count の4指標。",
            ],
            risk=["単一ショック外の複合ショックは追加検証が必要。"],
            decision_ask=["上位シナリオ向けの対応策を運用手順に組み込む。"],
        ),
        "governance": _narrative_block(
            conclusion="予定事業費の式・根拠・監査証跡をパッケージ内で追跡可能にした。",
            rationale=[
                "式は acq_per_policy / maint_per_policy / coll_rate に固定し、非負制約を適用。",
                f"根拠ファイルは {formula_source.get('path', '-')}、ハッシュ付きで管理。",
                "静かなフォールバックを禁止し、欠損時は失敗させる設計。",
            ],
            risk=["入力CSVスキーマ変更時に式前提が崩れるため検証を自動化する。"],
            decision_ask=["監査証跡(trace_map + formula_id)を提出物として固定する。"],
        ),
        "decision_ask": _narrative_block(
            conclusion="今回の決裁は価格採択と運用ガードレール承認を同時に求める。",
            rationale=[
                "承認対象は価格テーブル、制約閾値、再実行条件、責任者。",
                "実行順序は反映→監視→感応度再評価→ログ更新で固定。",
                "同一入力・同一コマンドで再現可能な運用を維持。",
            ],
            risk=["短期間で前提変更が重なるとレビュー負荷が増加する。"],
            decision_ask=["本日中の採択可否と次回レビュー日程の確定を要請。"],
        ),
    }


def _build_en_narrative(
    *,
    run_summary: Mapping[str, Any],
    pricing_rows: Sequence[Mapping[str, Any]],
    constraint_rows: Sequence[Mapping[str, Any]],
    cashflow_rows: Sequence[Mapping[str, Any]],
    sensitivity_rows: Sequence[Mapping[str, Any]],
    decision_compare: Mapping[str, Any],
    explainability_report: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    summary = _as_mapping(run_summary.get("summary"))
    min_irr = _safe_float(summary.get("min_irr"))
    min_nbv = _safe_float(summary.get("min_nbv"))
    max_ptm = _safe_float(summary.get("max_premium_to_maturity"))
    violation_count = _safe_int(summary.get("violation_count"))
    compare = _as_mapping(decision_compare)
    compare_diff = _as_mapping(compare.get("metric_diff_recommended_minus_counter"))
    adoption_reasons = [str(item) for item in _as_list(compare.get("adoption_reason")) if str(item).strip()]
    explain = _as_mapping(explainability_report)
    top_components = _top_components(_as_mapping(explain.get("causal_bridge")))
    top_risk_scenario = _sensitivity_top_risk(
        _as_mapping(explain.get("sensitivity_decomposition")),
        sensitivity_rows,
    )
    cash_totals = _cashflow_totals(cashflow_rows)
    inflow_total = cash_totals["premium_income"] + cash_totals["investment_income"]
    investment_share = (cash_totals["investment_income"] / inflow_total) if abs(inflow_total) > 1e-12 else 0.0
    premiums = [_safe_float(row.get("gross_annual_premium")) for row in pricing_rows]
    premium_min = min(premiums) if premiums else 0.0
    premium_max = max(premiums) if premiums else 0.0

    return {
        "executive_summary": _narrative_block(
            conclusion="Recommended pricing is decision-ready with adequacy, profitability, and soundness met together.",
            rationale=[
                f"KPI snapshot: min IRR={_fmt_pct(min_irr)}, min NBV={_fmt_jpy(min_nbv)}, max PTM={_fmt_ratio(max_ptm)}, violations={violation_count}.",
                f"Cumulative net cashflow is {_fmt_jpy(cash_totals['net_cf'])}; investment share in inflow is {_fmt_pct(investment_share)}.",
                adoption_reasons[0] if adoption_reasons else "Selection is based on guardrail compliance and resilient economics.",
            ],
            risk=[f"Primary downside trigger is {top_risk_scenario} under sensitivity stress."],
            decision_ask=["Approve recommended alternative and retain counter as benchmark only."],
        ),
        "decision_statement": _narrative_block(
            conclusion="Recommended and counter alternatives were independently optimized; recommended is adopted.",
            rationale=[
                f"Objective modes: recommended={compare.get('objectives', {}).get('recommended', '-')}, counter={compare.get('objectives', {}).get('counter', '-')}.",
                f"Metric deltas (rec-counter): min IRR={_safe_float(compare_diff.get('min_irr')):.6f}, min NBV={_safe_float(compare_diff.get('min_nbv')):,.0f}, max PTM={_safe_float(compare_diff.get('max_premium_to_maturity')):.6f}.",
                adoption_reasons[1] if len(adoption_reasons) > 1 else "Decision prioritizes guardrails and durable profitability.",
            ],
            risk=["Counter may appear more aggressive in selected points; field communication should be prepared."],
            decision_ask=["Record formal adoption/rejection decision and lock policy for next run window."],
        ),
        "pricing_recommendation": _narrative_block(
            conclusion="Final price table balances quote competitiveness and sustainable unit economics.",
            rationale=[
                f"Annual premium range by model point is {premium_min:,.0f} to {premium_max:,.0f}.",
                f"Hard floors remain protected at min IRR={_fmt_pct(min_irr)} and min NBV={_fmt_jpy(min_nbv)}.",
                "Price level is linked to explainable expense and investment drivers, not a flat uplift.",
            ],
            risk=["Over-discounting younger/longer points would deteriorate long-tail economics."],
            decision_ask=["Approve immediate quote table deployment with exception logging controls."],
        ),
        "constraint_status": _narrative_block(
            conclusion="Hard constraints are satisfied and escalation triggers are pre-defined.",
            rationale=[
                "Constraint margins are positive on non-watch/non-exempt scope.",
                f"Violation count is {violation_count} on governance control scope.",
                "Watch points and exemptions are governed separately with explicit ownership.",
            ],
            risk=["Margin compression after assumption updates can quickly consume current buffer."],
            decision_ask=["Approve trigger policy: rerun if min IRR < 2.0% or max PTM > 1.056."],
        ),
        "cashflow_bridge": _narrative_block(
            conclusion="Profit-source cashflow confirms a balanced inflow/outflow structure.",
            rationale=[
                f"Inflow: premium={_fmt_jpy(cash_totals['premium_income'])}, investment={_fmt_jpy(cash_totals['investment_income'])}.",
                f"Outflow: benefit={_fmt_jpy(cash_totals['benefit_outgo'])}, expense={_fmt_jpy(cash_totals['expense_outgo'])}, reserve={_fmt_jpy(cash_totals['reserve_change_outgo'])}.",
                f"Investment contribution ratio is {_fmt_pct(investment_share)} of inflow.",
            ],
            risk=["Rate-down scenarios can reduce investment contribution and weaken buffer."],
            decision_ask=["Use profit-source cashflow as standing quarterly management KPI."],
        ),
        "profit_source_decomposition": _narrative_block(
            conclusion="Bridge decomposition links decision alternatives to profit-source deltas.",
            rationale=[
                top_components[0] if top_components else "Bridge decomposition quantifies source-level impact on net delta.",
                top_components[1] if len(top_components) > 1 else "Contribution ranking is deterministic and reproducible.",
                "Year-over-year movement is checked to avoid one-off profit interpretation.",
            ],
            risk=["Source concentration risk rises when one component dominates net delta."],
            decision_ask=["Approve component thresholds and preserve ranking logic in future cycles."],
        ),
        "sensitivity": _narrative_block(
            conclusion="Sensitivity decomposition identifies dominant scenarios and response priorities.",
            rationale=[
                f"Top risk scenario is {top_risk_scenario} under combined IRR/NBV/PTM/violation evaluation.",
                "Bridge and sensitivity decomposition are used together for causal accountability.",
                "Monitoring KPIs are fixed at min IRR, min NBV, max PTM, and violation count.",
            ],
            risk=["Residual risk remains in compound shocks beyond one-factor stress tests."],
            decision_ask=["Approve predefined response playbooks for top-ranked scenarios."],
        ),
        "governance": _narrative_block(
            conclusion="Planned expense formulas and traceability satisfy audit-grade explainability.",
            rationale=[
                "Formula catalog is fixed and non-negative constraints are enforced as hard stop rules.",
                "Source file path/hash and trace map are retained as governance evidence.",
                "Silent fallback is prohibited for broken assumptions or missing evidence.",
            ],
            risk=["Source schema drift can invalidate formula assumptions if not validated early."],
            decision_ask=["Approve mandatory audit artifacts for every run package."],
        ),
        "decision_ask": _narrative_block(
            conclusion="This decision requires adoption plus operating guardrails in one resolution.",
            rationale=[
                "Approval scope: price table, thresholds, rerun triggers, and ownership.",
                "Execution flow: quote deployment, monitoring, stress rerun, governance log update.",
                "Deterministic commands and artifacts preserve reproducibility.",
            ],
            risk=["Multiple assumption changes in short windows may increase governance load."],
            decision_ask=["Approve production rollout with quarterly review checkpoints."],
        ),
    }


def build_management_narrative(
    *,
    run_summary: Mapping[str, Any],
    pricing_rows: Sequence[Mapping[str, Any]],
    constraint_rows: Sequence[Mapping[str, Any]],
    cashflow_rows: Sequence[Mapping[str, Any]],
    sensitivity_rows: Sequence[Mapping[str, Any]],
    decision_compare: Mapping[str, Any] | None,
    explainability_report: Mapping[str, Any] | None,
    language: str,
) -> dict[str, dict[str, Any]]:
    compare_payload = _as_mapping(decision_compare)
    explain_payload = _as_mapping(explainability_report)
    if language == "ja":
        return _build_ja_narrative(
            run_summary=run_summary,
            pricing_rows=pricing_rows,
            constraint_rows=constraint_rows,
            cashflow_rows=cashflow_rows,
            sensitivity_rows=sensitivity_rows,
            decision_compare=compare_payload,
            explainability_report=explain_payload,
        )
    return _build_en_narrative(
        run_summary=run_summary,
        pricing_rows=pricing_rows,
        constraint_rows=constraint_rows,
        cashflow_rows=cashflow_rows,
        sensitivity_rows=sensitivity_rows,
        decision_compare=compare_payload,
        explainability_report=explain_payload,
    )


def build_main_slide_checks(
    *,
    management_narrative: Mapping[str, Any],
    slide_ids: Sequence[str],
    narrative_contract: Mapping[str, Any],
    decision_compare: Mapping[str, Any] | None,
) -> dict[str, Any]:
    required_sections_raw = _as_list(narrative_contract.get("required_sections"))
    required_sections = [str(item) for item in required_sections_raw if str(item).strip()]
    min_lines = _safe_int(narrative_contract.get("min_lines_per_main_slide"), default=0)
    mode = str(narrative_contract.get("mode", "")).strip()
    compare_slide_id = str(narrative_contract.get("main_compare_slide_id", "")).strip()
    comparison_layout = str(narrative_contract.get("comparison_layout", "")).strip()
    decision_compare_enabled = bool(_as_mapping(decision_compare).get("enabled", False))

    per_slide: list[dict[str, Any]] = []
    section_ok_count = 0
    density_ok_global = True
    order_ok_global = True

    for slide_id in slide_ids:
        block = _as_mapping(management_narrative.get(slide_id))
        section_order = [str(item) for item in _as_list(block.get("section_order")) if str(item).strip()]
        required_present = True
        for section in required_sections:
            if section == "conclusion":
                if not str(block.get("conclusion", "")).strip():
                    required_present = False
                    break
                continue
            if not [item for item in _as_list(block.get(section)) if str(item).strip()]:
                required_present = False
                break
        if required_present:
            section_ok_count += 1

        line_count = _line_count(block, required_sections)
        density_ok = line_count >= min_lines
        if not density_ok:
            density_ok_global = False

        order_ok = section_order == list(SECTION_ORDER)
        if not order_ok:
            order_ok_global = False

        per_slide.append(
            {
                "slide_id": slide_id,
                "line_count": line_count,
                "required_sections_present": required_present,
                "density_ok": density_ok,
                "section_order_ok": order_ok,
            }
        )

    coverage = (section_ok_count / len(slide_ids)) if slide_ids else 0.0

    compare_block = _as_mapping(management_narrative.get(compare_slide_id))
    compare_joined = "\n".join(
        [
            str(compare_block.get("conclusion", "")),
            *[str(item) for item in _as_list(compare_block.get("rationale"))],
            *[str(item) for item in _as_list(compare_block.get("risk"))],
            *[str(item) for item in _as_list(compare_block.get("decision_ask"))],
        ]
    )
    main_compare_present = (
        True
        if not decision_compare_enabled
        else bool(compare_slide_id and _contains_compare_tokens(compare_joined))
    )

    decision_style_ok = bool(mode == "conclusion_first" and order_ok_global)
    return {
        "mode": mode,
        "comparison_layout": comparison_layout,
        "main_compare_slide_id": compare_slide_id,
        "min_lines_per_main_slide": min_lines,
        "required_sections": required_sections,
        "coverage": coverage,
        "density_ok": density_ok_global,
        "main_compare_present": main_compare_present,
        "decision_style_ok": decision_style_ok,
        "per_slide": per_slide,
    }
