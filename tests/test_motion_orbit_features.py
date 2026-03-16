from celestial_triage.features.extractor import extract_shared_features


def test_motion_and_orbit_scaffold_fields_present():
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
            "magnitude": 19.5,
            "moving_flag": 1,
            "catalog_match_status": "poor_match",
            "ra": 10.8,
            "dec": 10.2,
            "class_confidence": 0.25,
        },
        {
            "timestamp": "2026-03-15T02:00:00+00:00",
            "magnitude": 19.1,
            "moving_flag": 1,
            "catalog_match_status": "no_match",
            "ra": 11.5,
            "dec": 10.4,
            "class_confidence": 0.2,
        },
    ]

    f = extract_shared_features(detections)
    assert f["motion_rate_deg_per_hour"] > 0
    assert 0 <= f["motion_consistency_placeholder"] <= 1
    assert 0 <= f["direction_consistency_placeholder"] <= 1
    assert 0 <= f["orbit_fit_quality"] <= 1
    assert "eccentricity_placeholder" in f
    assert "hyperbolic_likelihood" in f
    assert "inbound_outbound_placeholder" in f
