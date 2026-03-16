from celestial_triage.config import DETECTOR_WEIGHTS
from celestial_triage.scoring.common import clamp01


def evaluate(features: dict) -> tuple[float, list[str]]:
    w = DETECTOR_WEIGHTS["iso_detector"]
    multi_detect = clamp01(features.get("detection_count", 0) / 5.0)
    consistency = clamp01(features.get("motion_consistency_placeholder", 0.0))
    direction_consistency = clamp01(features.get("direction_consistency_placeholder", 0.0))
    hyperbolic = clamp01(features.get("hyperbolic_likelihood", features.get("hyperbolic_likelihood_placeholder", 0.0)))
    eccentricity = clamp01((features.get("eccentricity_placeholder", 0.0) - 0.8) / 0.7)
    poor_catalog = clamp01(features.get("poor_catalog_fraction", 0.0))

    score = (
        0.45 * hyperbolic
        + 0.2 * eccentricity
        + 0.2 * poor_catalog
        + 0.15 * multi_detect
    )
    score = clamp01(score * (0.75 + 0.15 * consistency + 0.10 * direction_consistency))

    return clamp01(score), [
        f"hyperbolic={hyperbolic:.2f}",
        f"eccentricity={eccentricity:.2f}",
        f"poor_catalog={poor_catalog:.2f}",
        f"multi_detect={multi_detect:.2f}",
        f"direction_consistency={direction_consistency:.2f}",
    ]
