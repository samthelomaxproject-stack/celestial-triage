from celestial_triage.config import DETECTOR_WEIGHTS
from celestial_triage.scoring.common import clamp01


def evaluate(features: dict) -> tuple[float, list[str]]:
    w = DETECTOR_WEIGHTS["iso_detector"]
    score = (
        w["hyperbolic"] * clamp01(features.get("hyperbolic_likelihood_placeholder", 0.0))
        + w["poor_catalog"] * clamp01(features.get("poor_catalog_fraction", 0.0))
        + w["multi_detect"] * clamp01(features.get("detection_count", 0) / 5.0)
    )
    return clamp01(score), [
        f"hyperbolic={features.get('hyperbolic_likelihood_placeholder', 0):.2f}",
        f"poor_catalog={features.get('poor_catalog_fraction', 0):.2f}",
    ]
