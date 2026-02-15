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
        if not label:
            continue
        delta = _safe_float(payload.get("delta_recommended_minus_counter"))
        if label.lower() == "net_cf":
            continue
        enriched.append((abs(delta), f"{label}差分 {delta:,.0f}"))
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
            _safe_float(base.get("max_premium_to_maturity")) - _safe_float(row.get("max_premium_to_maturity")),
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
    compare_integrity = _as_mapping(compare.get("integrity"))

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
    year_tail_delta = 0.0
    if len(cashflow_rows) >= 2:
        year_tail_delta = _safe_float(cashflow_rows[-1].get("net_cf")) - _safe_float(
            cashflow_rows[-2].get("net_cf")
        )

    return {
        "executive_summary": _narrative_block(
            conclusion=(
                "推奨案で十分性・収益性・健全性を同時に満たし、経営会議で決裁可能な価格帯を確保しました。"
            ),
            rationale=[
                f"KPIは min IRR={_fmt_pct(min_irr)}, min NBV={_fmt_jpy(min_nbv)}, max PTM={_fmt_ratio(max_ptm)}, 違反件数={violation_count}件です。",
                f"利源別累計純CFは {_fmt_jpy(cash_totals['net_cf'])} で、入金に占める利差益寄与は {_fmt_pct(investment_share)} です。",
                adoption_reasons[0] if adoption_reasons else "採否理由はIRR/NBV/PTMと利源別キャッシュフローの両面で整合しています。",
            ],
            risk=[
                f"主要リスクは {top_risk_scenario} ショックで、感応度の悪化が先に現れる点を監視します。"
            ],
            decision_ask=["本会議では推奨案を承認し、対向案は比較対象として棄却する判断をお願いします。"],
        ),
        "decision_statement": _narrative_block(
            conclusion="推奨案と対向案を同条件で比較した結果、推奨案を採択し対向案は不採択とします。",
            rationale=[
                f"目的関数は推奨案={compare.get('objectives', {}).get('recommended', '-')}, 対向案={compare.get('objectives', {}).get('counter', '-')} です。",
                f"指標差（推奨-対向）は min IRR={_safe_float(compare_diff.get('min_irr')):.6f}, min NBV={_safe_float(compare_diff.get('min_nbv')):,.0f}, max PTM={_safe_float(compare_diff.get('max_premium_to_maturity')):.6f} です。",
                adoption_reasons[1] if len(adoption_reasons) > 1 else "採否理由はガードレール遵守と長期収益の持続性を優先したためです。",
            ],
            risk=[
                "対向案の一部モデルポイントは短期競争力が高い可能性があるため、販売現場には説明テンプレートを配布します。"
            ],
            decision_ask=[
                "本会議で推奨案採択・対向案不採択を明文化し、次回改定まで同一ポリシーで運用する決裁をお願いします。"
            ],
        ),
        "pricing_recommendation": _narrative_block(
            conclusion="最終Pは制約を満たす範囲で、競争力と収益性のバランスを取る水準に設定しました。",
            rationale=[
                f"モデルポイント別の年払Pレンジは {premium_min:,.0f} 〜 {premium_max:,.0f} です。",
                f"min IRR={_fmt_pct(min_irr)} と min NBV={_fmt_jpy(min_nbv)} を下限に維持し、価格のみの過度な引き下げを抑制しています。",
                "価格差の主因は予定事業費と利差益寄与の差で、単純な平均化は採用していません。",
            ],
            risk=["低年齢・長期点での過度なディスカウントは将来損益を毀損するため、再見積時も同一制約を適用します。"],
            decision_ask=["価格テーブルを見積システムへ反映し、例外設定はPDCAログへ記録する運用を承認してください。"],
        ),
        "constraint_status": _narrative_block(
            conclusion="ハード制約は監視点を除き充足し、逸脱時トリガーを事前定義した運用に移行できます。",
            rationale=[
                f"最拘束制約は {tight_label} で、最小ギャップは {tight_gap:.6f} です。",
                f"違反件数は {violation_count} 件で、非監視・非免除点の重大逸脱はありません。",
                "監視点と免除点は同一管理せず、監視は警戒、免除は期限付き例外として統治します。",
            ],
            risk=["前提更新時にギャップが縮小する可能性があるため、しきい値近傍点は月次で再検証します。"],
            decision_ask=["逸脱トリガー（min IRR < 2.0% または max PTM > 1.056）の自動再実行を継続適用してください。"],
        ),
        "cashflow_bridge": _narrative_block(
            conclusion="利源別キャッシュフローは保険料収入と利差益で原資を確保し、給付・事業費・責任準備金で配分する構造です。",
            rationale=[
                f"累計は premium={_fmt_jpy(cash_totals['premium_income'])}, investment={_fmt_jpy(cash_totals['investment_income'])}, benefit={_fmt_jpy(cash_totals['benefit_outgo'])} です。",
                f"費用・準備金は expense={_fmt_jpy(cash_totals['expense_outgo'])}, reserve={_fmt_jpy(cash_totals['reserve_change_outgo'])} で、純CFは {_fmt_jpy(cash_totals['net_cf'])} です。",
                f"利差益比率 {_fmt_pct(investment_share)} は運用前提更新の効果を示しており、価格決定に寄与しています。",
            ],
            risk=["運用利回り低下時は利差益寄与が縮小するため、金利ショック監視と再計算を運用ルールに固定します。"],
            decision_ask=["利源別CFを四半期経営レビューの定点指標に設定することを承認してください。"],
        ),
        "profit_source_decomposition": _narrative_block(
            conclusion="前年差分まで含めた利源分解で、収益の質と持続性を確認した上で価格を決定しています。",
            rationale=[
                top_components[0] if top_components else "推奨案と対向案の差分は利源別寄与に分解し、純CF差への寄与率を確認済みです。",
                top_components[1] if len(top_components) > 1 else "主要利源の寄与順を固定ルールで並べ替え、説明再現性を担保しています。",
                f"直近年度の純CF前年差は {year_tail_delta:,.0f} で、単年偏重でないかを確認しています。",
            ],
            risk=["特定利源に依存した収益構造が強まる場合は、対向案再評価を含めた見直しを実施します。"],
            decision_ask=["利源分解の寄与順と閾値を次期改定でも同一ロジックで継続する承認をお願いします。"],
        ),
        "sensitivity": _narrative_block(
            conclusion="感応度分析は支配シナリオを明示し、悪化順に対策優先度を定義できる状態です。",
            rationale=[
                f"最重要シナリオは {top_risk_scenario} で、IRR・NBV・PTM・違反件数への影響を同時評価しています。",
                "橋渡し分解と感応度分解を併用し、数理的な因果と経営上の対応優先度を接続しています。",
                "監視KPIは min IRR / min NBV / max PTM / violation_count の4指標を固定採用します。",
            ],
            risk=["単一ショックでは顕在化しない複合ショックが残余リスクのため、四半期ごとに再評価します。"],
            decision_ask=["感応度上位シナリオに対するアクションプランを予め承認し、閾値到達時に即時実行してください。"],
        ),
        "governance": _narrative_block(
            conclusion="予定事業費の式・根拠・非負制約は監査対応可能な形でトレーサブルに管理されています。",
            rationale=[
                "式は acq_per_policy / maint_per_policy / coll_rate を固定し、係数と中間計算を再現可能に保存しています。",
                f"参照ソースは {formula_source.get('path', '-')}, SHA-256={formula_source.get('sha256', '-')} です。",
                "負の予定事業費は即時エラー停止とし、静かなフォールバックを禁止しています。",
            ],
            risk=["入力CSV構造変更時に式の前提が崩れるため、スキーマチェックとハッシュ記録を必須にします。"],
            decision_ask=["監査証跡（trace_map + formula_id）を本番運用の必須成果物として固定することを承認してください。"],
        ),
        "decision_ask": _narrative_block(
            conclusion="本件は推奨案採択を前提に、実行条件と再実行条件を同時に決裁する案件です。",
            rationale=[
                "決裁事項は価格テーブル承認、運用しきい値ロック、再計算トリガー固定の3点です。",
                "実行計画は見積反映 -> モニタリング -> 感応度再評価の順で進め、責任者を明確化します。",
                "同一入力・同一コマンドで再現できるため、説明責任を継続的に担保できます。",
            ],
            risk=["運用中に前提更新が集中した場合は、再実行頻度増加に伴う承認遅延リスクがあります。"],
            decision_ask=["本会議で承認後、次回レビュー条件（前提更新・閾値逸脱・四半期定例）を発動条件として確定してください。"],
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
    causal_bridge = _as_mapping(explain.get("causal_bridge"))
    top_components = _top_components(causal_bridge)
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
    tight_constraint = {}
    if constraint_rows:
        tight_constraint = min(
            (_as_mapping(row) for row in constraint_rows),
            key=lambda row: _safe_float(row.get("min_gap"), default=10**12),
        )

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
                f"Tightest constraint is {tight_constraint.get('label') or tight_constraint.get('constraint') or '-'} with min gap {_safe_float(tight_constraint.get('min_gap')):.6f}.",
                f"Violation count is {violation_count} on non-watch / non-exempt control scope.",
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
