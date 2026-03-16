from typing import Any


def _detector_to_label(detector_name: str) -> str:
    mapping = {
        "satellite_detector": "satellite-like",
        "neo_detector": "neo-like",
        "unknown_mover_detector": "unknown-mover-like",
        "kbo_detector": "kbo-like",
        "iso_detector": "iso-like",
        "deep_anomaly_detector": "deep-anomaly-like",
    }
    return mapping.get(detector_name, detector_name)


def _confidence_label(primary_score: float, gap: float, features: dict[str, Any]) -> str:
    detection_count = float(features.get("detection_count", 0) or 0)
    orbit_quality = float(features.get("orbit_fit_quality", 0) or 0)
    poor_catalog = float(features.get("poor_catalog_fraction", 0) or 0)

    confidence_points = 0.0
    confidence_points += 0.45 * min(1.0, primary_score)
    confidence_points += 0.25 * min(1.0, gap / 0.35)
    confidence_points += 0.20 * min(1.0, detection_count / 6.0)
    confidence_points += 0.10 * min(1.0, orbit_quality)

    # if catalog agreement is poor, certainty framing is reduced a bit
    confidence_points -= 0.10 * min(1.0, poor_catalog)

    if confidence_points >= 0.72:
        return "strong"
    if confidence_points >= 0.45:
        return "moderate"
    return "weak"


def build_interpretation_summary(features: dict[str, Any], score_map: dict[str, float]) -> dict[str, Any]:
    if not score_map:
        return {
            "primary_interpretation": "unknown",
            "primary_detector": "",
            "confidence": "weak",
            "top_score": 0.0,
            "runner_up_detector": "",
            "runner_up_score": 0.0,
            "score_gap": 0.0,
            "competing_interpretations": [],
            "conflict_severity": "none",
            "ambiguity_notes": ["No detector scores available"],
            "explanation": "No detector evidence available.",
        }

    ordered = sorted(score_map.items(), key=lambda kv: kv[1], reverse=True)
    top_det, top_score = ordered[0]
    run_det, run_score = ordered[1] if len(ordered) > 1 else ("", 0.0)
    gap = max(0.0, float(top_score) - float(run_score))

    competing = [
        _detector_to_label(det)
        for det, sc in ordered[1:]
        if sc >= max(0.5, float(top_score) - 0.12)
    ]

    if len(competing) >= 2 or gap < 0.1:
        severity = "high"
    elif len(competing) == 1 or gap < 0.2:
        severity = "medium"
    else:
        severity = "low"

    confidence = _confidence_label(float(top_score), gap, features)

    notes: list[str] = []
    if severity == "high":
        notes.append("Multiple detectors show similar strength; interpretation is ambiguous.")
    elif severity == "medium":
        notes.append("A competing detector remains plausible.")
    else:
        notes.append("Primary interpretation has a clear score lead.")

    if float(features.get("detection_count", 0) or 0) < 3:
        notes.append("Limited detection history reduces confidence.")
    if float(features.get("poor_catalog_fraction", 0) or 0) > 0.5:
        notes.append("Poor catalog agreement may indicate unresolved classification uncertainty.")

    explanation = (
        f"Primary interpretation is {_detector_to_label(top_det)} based on top detector score "
        f"{float(top_score):.3f} with score gap {gap:.3f} over runner-up "
        f"{_detector_to_label(run_det) if run_det else 'none'}"
    )

    return {
        "primary_interpretation": _detector_to_label(top_det),
        "primary_detector": top_det,
        "confidence": confidence,
        "top_score": round(float(top_score), 3),
        "runner_up_detector": run_det,
        "runner_up_score": round(float(run_score), 3),
        "score_gap": round(gap, 3),
        "competing_interpretations": competing,
        "conflict_severity": severity,
        "ambiguity_notes": notes,
        "explanation": explanation,
    }
