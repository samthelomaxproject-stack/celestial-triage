from celestial_triage.detectors.satellite_detector import evaluate


def test_satellite_detector_scores_reasonably_with_missing_quality_features():
    # The detector now down-weights scores when motion consistency/trajectory
    # quality are absent (defaults to 0.0), so this should remain moderate.
    features = {
        "moving_fraction": 0.9,
        "poor_catalog_fraction": 0.8,
        "angular_motion_placeholder": 4.0,
    }
    score, reasons = evaluate(features)
    assert 0.55 <= score <= 0.60
    assert len(reasons) >= 5


def test_satellite_detector_scores_high_with_strong_quality_features():
    features = {
        "moving_fraction": 0.9,
        "poor_catalog_fraction": 0.8,
        "angular_motion_placeholder": 4.0,
        "motion_consistency_placeholder": 1.0,
        "trajectory_quality": 1.0,
    }
    score, _ = evaluate(features)
    assert score > 0.8
