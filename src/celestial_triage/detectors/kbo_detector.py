from celestial_triage.config import DETECTOR_WEIGHTS
from celestial_triage.scoring.common import clamp01


def evaluate(features: dict) -> tuple[float, list[str]]:
    w = DETECTOR_WEIGHTS["kbo_detector"]
    slow_motion = clamp01(1.0 - min(1.0, features.get("angular_motion_placeholder", 0.0) / 3.0))
    dim = clamp01((features.get("avg_magnitude", 0.0) - 18.0) / 8.0)
    persistence = clamp01(features.get("detection_span_hours", 0.0) / 72.0)
    score = w["slow_motion"] * slow_motion + w["dim"] * dim + w["persistence"] * persistence
    return clamp01(score), [f"slow_motion={slow_motion:.2f}", f"dim={dim:.2f}", f"persistence={persistence:.2f}"]
