from __future__ import annotations

from typing import Any, Mapping


_HIGHER_IS_BETTER = {
    "min_irr",
    "min_nbv",
    "min_loading_surplus_ratio",
}
_LOWER_IS_BETTER = {
    "max_premium_to_maturity",
    "violation_count",
}


def _safe_float(value: object, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _metric_score(metric: str, current: float, peer: float) -> float:
    if metric in _HIGHER_IS_BETTER:
        return current - peer
    if metric in _LOWER_IS_BETTER:
        return peer - current
    return current - peer


def _quant_text(
    *,
    metric: str,
    current: float,
    peer: float,
    is_pro: bool,
    language: str,
) -> str:
    delta = current - peer
    if language == "ja":
        metric_labels = {
            "min_irr": "最小IRR",
            "min_nbv": "最小NBV",
            "min_loading_surplus_ratio": "最小Loading surplus比率",
            "max_premium_to_maturity": "最大PTM",
            "violation_count": "違反件数",
        }
        label = metric_labels.get(metric, metric)
        if metric == "violation_count":
            return (
                f"{label}は{current:.0f}件（比較案 {peer:.0f}件）で、"
                f"{'優位' if is_pro else '劣位'}差は{abs(delta):.0f}件。"
            )
        if metric in {"min_irr", "min_loading_surplus_ratio"}:
            return (
                f"{label}は{current * 100:.2f}%（比較案 {peer * 100:.2f}%）で、"
                f"{'改善' if is_pro else '劣化'}幅は{abs(delta) * 100:.2f}pt。"
            )
        if metric == "max_premium_to_maturity":
            return (
                f"{label}は{current:.4f}（比較案 {peer:.4f}）で、"
                f"{'低位' if is_pro else '高位'}差は{abs(delta):.4f}。"
            )
        return (
            f"{label}は{current:,.0f}（比較案 {peer:,.0f}）で、"
            f"{'改善' if is_pro else '劣化'}差は{abs(delta):,.0f}。"
        )

    if metric == "violation_count":
        return (
            f"{metric}={current:.0f} vs peer {peer:.0f}, "
            f"{'advantage' if is_pro else 'disadvantage'} by {abs(delta):.0f}."
        )
    if metric in {"min_irr", "min_loading_surplus_ratio"}:
        return (
            f"{metric}={current * 100:.2f}% vs peer {peer * 100:.2f}%, "
            f"{'improvement' if is_pro else 'deterioration'} {abs(delta) * 100:.2f}pt."
        )
    return (
        f"{metric}={current:.4f} vs peer {peer:.4f}, "
        f"{'improvement' if is_pro else 'deterioration'} {abs(delta):.4f}."
    )


def _qual_templates(objective_mode: str, language: str) -> tuple[list[str], list[str]]:
    if language == "ja":
        if objective_mode == "maximize_min_irr":
            pros = [
                "最小IRRの底上げを優先し、下振れ局面での経営耐性を確保しやすい。",
                "制約逸脱の監視線が明確で、価格改定の説明が監査に通しやすい。",
                "逆ざや回避の姿勢を明示でき、長期の資本健全性を守りやすい。",
            ]
            cons = [
                "収益性防衛を優先する分、一部モデルポイントで価格競争力を失う可能性がある。",
                "販売現場では料率差の理由説明が必要になり、運用負荷が増える。",
                "短期の販売量最大化よりも、長期健全性を重視するトレードオフが生じる。",
            ]
            return pros, cons
        pros = [
            "十分性・収益性・健全性のバランスを取り、採算と販売性の両立を狙える。",
            "既存運用と整合しやすく、導入時の変更負荷が比較的小さい。",
            "目的関数の構造が単純で、再現実行とレビューが容易。",
        ]
        cons = [
            "均衡設計のため、最悪点IRRの改善余地を取り切れない可能性がある。",
            "将来の前提悪化に対する耐性は、保守型設計より弱くなる場合がある。",
            "経営判断として何を最優先したかが、明示しないと伝わりにくい。",
        ]
        return pros, cons

    if objective_mode == "maximize_min_irr":
        return (
            [
                "Prioritizes downside IRR protection and improves stress resilience.",
                "Governance thresholds are explicit, making audit narratives clearer.",
                "Defends long-term capital soundness by reducing underpricing risk.",
            ],
            [
                "May weaken quote competitiveness for some model points.",
                "Requires clearer field communication on pricing rationale.",
                "Trades short-term volume upside for long-term stability.",
            ],
        )
    return (
        [
            "Balances adequacy, profitability, and soundness in one objective.",
            "Closer to current operating practice with lower transition cost.",
            "Simple objective structure supports reproducible reruns.",
        ],
        [
            "Can leave minimum-IRR improvement on the table versus max-min-IRR mode.",
            "Stress resilience may be weaker than a conservative objective.",
            "Priority ordering can look ambiguous without explicit governance narrative.",
        ],
    )


def build_procon_bundle(
    *,
    alternative_id: str,
    objective_mode: str,
    metrics: Mapping[str, object],
    peer_metrics: Mapping[str, object] | None,
    quant_count: int,
    qual_count: int,
    language: str,
) -> dict[str, Any]:
    metric_keys = [
        "min_irr",
        "min_nbv",
        "min_loading_surplus_ratio",
        "max_premium_to_maturity",
        "violation_count",
    ]
    peer = peer_metrics or metrics

    scored: list[dict[str, Any]] = []
    for key in metric_keys:
        current = _safe_float(metrics.get(key))
        peer_value = _safe_float(peer.get(key))
        score = _metric_score(key, current, peer_value)
        scored.append(
            {
                "metric": key,
                "current": current,
                "peer": peer_value,
                "score": score,
                "abs_score": abs(score),
            }
        )

    scored_desc = sorted(scored, key=lambda item: item["score"], reverse=True)
    scored_asc = sorted(scored, key=lambda item: item["score"])

    quant_pros: list[dict[str, Any]] = []
    for item in scored_desc[:quant_count]:
        quant_pros.append(
            {
                "metric": item["metric"],
                "text": _quant_text(
                    metric=item["metric"],
                    current=item["current"],
                    peer=item["peer"],
                    is_pro=True,
                    language=language,
                ),
                "evidence": {
                    "current": item["current"],
                    "peer": item["peer"],
                    "delta": item["current"] - item["peer"],
                },
            }
        )

    quant_cons: list[dict[str, Any]] = []
    for item in scored_asc[:quant_count]:
        quant_cons.append(
            {
                "metric": item["metric"],
                "text": _quant_text(
                    metric=item["metric"],
                    current=item["current"],
                    peer=item["peer"],
                    is_pro=False,
                    language=language,
                ),
                "evidence": {
                    "current": item["current"],
                    "peer": item["peer"],
                    "delta": item["current"] - item["peer"],
                },
            }
        )

    pros_qual_src, cons_qual_src = _qual_templates(objective_mode, language)
    qual_pros = [
        {"id": f"qual_pro_{idx+1}", "text": text}
        for idx, text in enumerate(pros_qual_src[:qual_count])
    ]
    qual_cons = [
        {"id": f"qual_con_{idx+1}", "text": text}
        for idx, text in enumerate(cons_qual_src[:qual_count])
    ]

    while len(qual_pros) < qual_count:
        qual_pros.append({"id": f"qual_pro_{len(qual_pros)+1}", "text": pros_qual_src[-1]})
    while len(qual_cons) < qual_count:
        qual_cons.append({"id": f"qual_con_{len(qual_cons)+1}", "text": cons_qual_src[-1]})

    return {
        "alternative_id": alternative_id,
        "pros": {
            "quant": quant_pros[:quant_count],
            "qual": qual_pros[:qual_count],
        },
        "cons": {
            "quant": quant_cons[:quant_count],
            "qual": qual_cons[:qual_count],
        },
    }


def validate_procon_cardinality(
    *,
    procon_map: Mapping[str, Any],
    quant_count: int,
    qual_count: int,
) -> bool:
    if not isinstance(procon_map, Mapping) or not procon_map:
        return False
    for _, bundle in procon_map.items():
        if not isinstance(bundle, Mapping):
            return False
        pros = bundle.get("pros", {})
        cons = bundle.get("cons", {})
        if not isinstance(pros, Mapping) or not isinstance(cons, Mapping):
            return False
        pros_quant = pros.get("quant", [])
        pros_qual = pros.get("qual", [])
        cons_quant = cons.get("quant", [])
        cons_qual = cons.get("qual", [])
        if len(pros_quant) < quant_count:
            return False
        if len(cons_quant) < quant_count:
            return False
        if len(pros_qual) < qual_count:
            return False
        if len(cons_qual) < qual_count:
            return False
    return True
