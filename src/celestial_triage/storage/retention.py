from datetime import datetime, timedelta, timezone

from celestial_triage.config import RETENTION_THRESHOLDS


def assign_retention_tier(max_score: float, detection_count: int, reviewed: bool, poor_catalog_fraction: float, hyperbolic_hint: float, manual_keep: bool = False) -> tuple[str, bool, bool, str | None, str]:
    now = datetime.now(timezone.utc)

    if manual_keep:
        return "cold", True, True, None, "manual retention flag"
    if max_score >= RETENTION_THRESHOLDS["hot_min_score"] or hyperbolic_hint > 0.7:
        return "hot", True, True, (now + timedelta(days=30)).isoformat(), "high score or hyperbolic hint"
    if max_score >= RETENTION_THRESHOLDS["warm_min_score"] or poor_catalog_fraction > 0.5 or detection_count >= 4:
        return "warm", True, True, (now + timedelta(days=90)).isoformat(), "interesting candidate evidence"
    if reviewed and max_score >= RETENTION_THRESHOLDS["cold_reviewed_min_score"]:
        return "cold", False, True, None, "reviewed with moderate interest"
    return "disposable", False, False, (now + timedelta(days=14)).isoformat(), "low score and explained"
