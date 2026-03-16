from typing import Any


def _band(score: float) -> str:
    if score >= 0.85:
        return "urgent"
    if score >= 0.65:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def build_followup_priority(
    features: dict[str, Any],
    score_map: dict[str, float],
    review_state: str,
) -> dict[str, Any]:
    iso = float(score_map.get("iso_detector", 0.0))
    motion_rate = float(features.get("motion_rate_deg_per_hour", 0.0) or 0.0)
    span = float(features.get("detection_span_hours", 0.0) or 0.0)
    poor_catalog = float(features.get("poor_catalog_fraction", 0.0) or 0.0)
    hyperbolic = float(features.get("hyperbolic_likelihood", 0.0) or 0.0)

    reasons: list[str] = []

    score = 0.0
    score += 0.35 * iso
    score += 0.20 * min(1.0, motion_rate / 2.0)
    score += 0.15 * min(1.0, span / 72.0)
    score += 0.15 * poor_catalog
    score += 0.15 * hyperbolic

    if iso >= 0.7:
        reasons.append("High ISO detector score")
    if motion_rate >= 1.0:
        reasons.append("Elevated apparent motion rate")
    if span >= 24:
        reasons.append("Multi-epoch persistence")
    if poor_catalog >= 0.5:
        reasons.append("Weak/poor catalog agreement")
    if hyperbolic >= 0.6:
        reasons.append("Hyperbolic-like orbital heuristic signal")

    # Review-state modulation
    if review_state == "follow-up":
        score = min(1.0, score + 0.1)
        reasons.append("Already marked follow-up by analyst")
    elif review_state == "dismissed":
        score = max(0.0, score - 0.2)
        reasons.append("Previously dismissed by analyst")

    return {
        "priority_score": round(score, 3),
        "priority": _band(score),
        "reasons": reasons or ["No strong follow-up triggers"],
    }
