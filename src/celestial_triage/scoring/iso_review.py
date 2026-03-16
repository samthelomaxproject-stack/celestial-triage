from typing import Any


def build_iso_review_signal(features: dict[str, Any], scores: list[dict[str, Any]]) -> dict[str, Any]:
    score_map = {s.get("detector_name"): float(s.get("score", 0.0)) for s in scores}
    iso = score_map.get("iso_detector", 0.0)
    neo = score_map.get("neo_detector", 0.0)
    kbo = score_map.get("kbo_detector", 0.0)

    competing: list[str] = []
    if neo >= 0.45:
        competing.append("neo_detector")
    if kbo >= 0.45:
        competing.append("kbo_detector")

    follow_up: list[str] = []
    if features.get("detection_count", 0) < 4:
        follow_up.append("Acquire more detections to improve trajectory confidence")
    if features.get("orbit_fit_quality", 0.0) < 0.45:
        follow_up.append("Attempt improved orbit-fit with additional cadence")
    if features.get("hyperbolic_likelihood", 0.0) > 0.6:
        follow_up.append("Prioritize astrometric follow-up to test hyperbolic hypothesis")
    if features.get("poor_catalog_fraction", 0.0) > 0.5:
        follow_up.append("Cross-check with additional catalogs and broker annotations")

    interpretation = "iso_favored" if iso > max(neo, kbo) else "competing_interpretations"

    summary_reasons = [
        f"iso_score={iso:.3f}",
        f"hyperbolic_likelihood={float(features.get('hyperbolic_likelihood', 0.0)):.3f}",
        f"eccentricity_placeholder={float(features.get('eccentricity_placeholder', 0.0)):.3f}",
        f"motion_rate_deg_per_hour={float(features.get('motion_rate_deg_per_hour', 0.0)):.3f}",
        f"direction_consistency={float(features.get('direction_consistency_placeholder', 0.0)):.3f}",
        f"inbound_outbound={features.get('inbound_outbound_placeholder', 'unknown')}",
    ]

    return {
        "interpretation": interpretation,
        "iso_score": iso,
        "competing_detectors": competing,
        "summary_reasons": summary_reasons,
        "follow_up": follow_up,
    }
