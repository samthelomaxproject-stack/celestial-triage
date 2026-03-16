from celestial_triage.detectors.satellite_detector import evaluate


def test_satellite_detector_scores_reasonably():
    features = {
        "moving_fraction": 0.9,
        "poor_catalog_fraction": 0.8,
        "angular_motion_placeholder": 4.0,
    }
    score, reasons = evaluate(features)
    assert score > 0.7
    assert len(reasons) >= 2
