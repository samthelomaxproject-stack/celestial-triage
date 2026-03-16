from celestial_triage.config import DETECTOR_WEIGHTS
from celestial_triage.scoring.common import clamp01


def evaluate(features: dict) -> tuple[float, list[str]]:
    w = DETECTOR_WEIGHTS["neo_detector"]
    brightness = clamp01((22.5 - features.get("avg_magnitude", 25.0)) / 10.0)
    span = clamp01(features.get("detection_span_hours", 0.0) / 48.0)
    score = (
        w["moving"] * clamp01(features.get("moving_fraction", 0.0))
        + w["brightness"] * brightness
        + w["span"] * span
    )
    return clamp01(score), [f"brightness={brightness:.2f}", f"span={span:.2f}"]
