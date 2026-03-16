from celestial_triage.config import DETECTOR_WEIGHTS
from celestial_triage.scoring.common import clamp01


def evaluate(features: dict) -> tuple[float, list[str]]:
    w = DETECTOR_WEIGHTS["satellite_detector"]
    fast_motion = clamp01(features.get("angular_motion_placeholder", 0.0) / 5.0)
    consistency = clamp01(features.get("motion_consistency_placeholder", 0.0))
    score = (
        w["moving"] * clamp01(features.get("moving_fraction", 0.0))
        + w["poor_catalog"] * clamp01(features.get("poor_catalog_fraction", 0.0))
        + w["fast_motion"] * fast_motion
    )
    score = clamp01(score * (0.85 + 0.15 * consistency))
    reasons = [
        f"moving_fraction={features.get('moving_fraction', 0):.2f}",
        f"poor_catalog_fraction={features.get('poor_catalog_fraction', 0):.2f}",
        f"fast_motion={fast_motion:.2f}",
        f"motion_consistency={consistency:.2f}",
    ]
    return clamp01(score), reasons
