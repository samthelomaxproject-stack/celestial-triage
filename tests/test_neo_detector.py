from celestial_triage.detectors.neo_detector import evaluate


def test_neo_detector_scores_moving_bright_candidate_higher():
    high_features = {
        "moving_fraction": 0.9,
        "avg_magnitude": 17.5,
        "detection_span_hours": 30.0,
    }
    low_features = {
        "moving_fraction": 0.1,
        "avg_magnitude": 24.5,
        "detection_span_hours": 1.0,
    }

    high_score, _ = evaluate(high_features)
    low_score, _ = evaluate(low_features)

    assert high_score > low_score
