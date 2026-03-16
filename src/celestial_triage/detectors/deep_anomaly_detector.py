from celestial_triage.config import DETECTOR_WEIGHTS
from celestial_triage.scoring.common import clamp01


def evaluate(features: dict) -> tuple[float, list[str]]:
    w = DETECTOR_WEIGHTS["deep_anomaly_detector"]
    low_conf = clamp01(1.0 - features.get("orbit_fit_placeholder", 0.0))
    mag_jump = clamp01(features.get("mag_delta_abs", 0.0) / 2.5)
    odd_combo = clamp01(features.get("anomaly_index_placeholder", 0.0))
    score = w["low_confidence"] * low_conf + w["mag_jump"] * mag_jump + w["odd_combo"] * odd_combo
    return clamp01(score), [f"low_conf={low_conf:.2f}", f"mag_jump={mag_jump:.2f}", f"odd_combo={odd_combo:.2f}"]
