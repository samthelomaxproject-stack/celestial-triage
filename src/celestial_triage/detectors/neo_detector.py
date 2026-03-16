from celestial_triage.config import DETECTOR_WEIGHTS
from celestial_triage.scoring.common import clamp01


def evaluate(features: dict) -> tuple[float, list[str]]:
    w = DETECTOR_WEIGHTS["neo_detector"]
    brightness = clamp01((22.5 - features.get("avg_magnitude", 25.0)) / 10.0)
    span = clamp01(features.get("detection_span_hours", 0.0) / 48.0)
    consistency = clamp01(features.get("motion_consistency_placeholder", 0.0))
    motion_rate = clamp01(features.get("motion_rate_deg_per_hour", 0.0) / 2.5)
    orbit_quality = clamp01(features.get("orbit_fit_quality", 0.0))

    # Separation from ISO: downweight explicitly hyperbolic/eccentric behavior.
    hyperbolic = clamp01(features.get("hyperbolic_likelihood", 0.0))
    eccentricity = clamp01((features.get("eccentricity_placeholder", 0.0) - 0.8) / 0.7)
    non_iso_penalty = 1.0 - 0.25 * max(hyperbolic, eccentricity)

    score = (
        w["moving"] * clamp01(features.get("moving_fraction", 0.0))
        + w["brightness"] * brightness
        + w["span"] * span
    )
    score = clamp01(score * (0.7 + 0.15 * consistency + 0.15 * motion_rate) * (0.85 + 0.15 * orbit_quality))
    score = clamp01(score * non_iso_penalty)

    return clamp01(score), [
        f"brightness={brightness:.2f}",
        f"span={span:.2f}",
        f"motion_rate={motion_rate:.2f}",
        f"motion_consistency={consistency:.2f}",
        f"orbit_fit_quality={orbit_quality:.2f}",
        f"iso_penalty_factor={non_iso_penalty:.2f}",
    ]
