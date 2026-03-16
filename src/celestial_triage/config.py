from pathlib import Path

DB_PATH = Path("celestial_triage.db")

DETECTOR_WEIGHTS = {
    "satellite_detector": {"moving": 0.35, "poor_catalog": 0.30, "fast_motion": 0.35},
    "neo_detector": {"moving": 0.45, "brightness": 0.25, "span": 0.30},
    "unknown_mover_detector": {"moving": 0.5, "unknown_class": 0.5},
    "kbo_detector": {"slow_motion": 0.5, "dim": 0.3, "persistence": 0.2},
    "iso_detector": {"hyperbolic": 0.5, "poor_catalog": 0.3, "multi_detect": 0.2},
    "deep_anomaly_detector": {"low_confidence": 0.3, "mag_jump": 0.4, "odd_combo": 0.3},
}

RETENTION_THRESHOLDS = {
    "hot_min_score": 0.75,
    "warm_min_score": 0.45,
    "cold_reviewed_min_score": 0.25,
}
