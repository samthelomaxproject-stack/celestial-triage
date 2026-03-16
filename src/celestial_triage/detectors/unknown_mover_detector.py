from celestial_triage.config import DETECTOR_WEIGHTS
from celestial_triage.scoring.common import clamp01


def evaluate(features: dict) -> tuple[float, list[str]]:
    w = DETECTOR_WEIGHTS["unknown_mover_detector"]
    unknown_class = clamp01(1.0 - features.get("avg_class_confidence", 0.0))
    multi_detect = clamp01(features.get("detection_count", 0) / 5.0)
    score = w["moving"] * clamp01(features.get("moving_fraction", 0.0)) + w["unknown_class"] * unknown_class
    score = clamp01(score * (0.8 + 0.2 * multi_detect))
    return clamp01(score), [f"unknown_class={unknown_class:.2f}", f"multi_detect={multi_detect:.2f}"]
