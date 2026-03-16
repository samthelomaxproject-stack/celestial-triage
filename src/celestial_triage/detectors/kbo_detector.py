from celestial_triage.config import DETECTOR_WEIGHTS
from celestial_triage.scoring.common import clamp01


def evaluate(features: dict) -> tuple[float, list[str]]:
    w = DETECTOR_WEIGHTS["kbo_detector"]
    slow_motion = clamp01(1.0 - min(1.0, features.get("motion_rate_deg_per_hour", 0.0) / 0.5))
    dim = clamp01((features.get("avg_magnitude", 0.0) - 18.0) / 8.0)
    persistence = clamp01(features.get("detection_span_hours", 0.0) / 72.0)
    consistency = clamp01(features.get("motion_consistency_placeholder", 0.0))
    orbit_quality = clamp01(features.get("orbit_fit_quality", 0.0))
    score = w["slow_motion"] * slow_motion + w["dim"] * dim + w["persistence"] * persistence
    score = clamp01(score * (0.75 + 0.15 * consistency + 0.10 * orbit_quality))
    return clamp01(score), [
        f"slow_motion={slow_motion:.2f}",
        f"dim={dim:.2f}",
        f"persistence={persistence:.2f}",
        f"motion_consistency={consistency:.2f}",
        f"orbit_fit_quality={orbit_quality:.2f}",
    ]
