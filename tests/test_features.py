from celestial_triage.features.extractor import extract_shared_features


def test_feature_extraction_core_values():
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
            "timestamp": "2026-03-15T02:00:00+00:00",
            "magnitude": 19.0,
            "moving_flag": 0,
            "catalog_match_status": "matched",
            "ra": 11.0,
            "dec": 10.0,
            "class_confidence": 0.3,
        },
    ]
    f = extract_shared_features(detections)
    assert f["detection_count"] == 2
    assert f["detection_span_hours"] == 2.0
    assert f["mag_delta_abs"] == 1.0
