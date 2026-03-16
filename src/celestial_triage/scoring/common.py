def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def score_band(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"
