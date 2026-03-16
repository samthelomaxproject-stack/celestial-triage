from celestial_triage.features.extractor import extract_shared_features


def test_trajectory_quality_fields_present_and_bounded():
    detections = [
        {
            "timestamp": "2026-03-15T00:00:00+00:00",
            "magnitude": 20.0,
            "moving_flag": 1,
            "catalog_match_status": "no_match",
            "ra": 10.0,
            "dec": 10.0,
            "class_confidence": 0.2,
        },
        {
            "timestamp": "2026-03-15T01:00:00+00:00",
            "magnitude": 19.8,
            "moving_flag": 1,
            "catalog_match_status": "poor_match",
            "ra": 10.5,
            "dec": 10.2,
            "class_confidence": 0.25,
        },
        {
            "timestamp": "2026-03-15T02:00:00+00:00",
            "magnitude": 19.7,
            "moving_flag": 1,
            "catalog_match_status": "poor_match",
            "ra": 11.0,
            "dec": 10.4,
            "class_confidence": 0.25,
        },
    ]

    f = extract_shared_features(detections)
    assert 0 <= f["heading_change_consistency"] <= 1
    assert 0 <= f["path_smoothness_placeholder"] <= 1
    assert 0 <= f["trajectory_quality"] <= 1
