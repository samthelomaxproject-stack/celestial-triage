from celestial_triage.features.orbit import compute_orbit_scaffold_features


def test_orbit_refinement_outputs_expected_ranges():
    f = compute_orbit_scaffold_features(
        motion_rate_deg_per_hour=1.4,
        motion_consistency=0.8,
        poor_catalog_fraction=0.7,
        detection_count=6,
        detection_span_hours=48,
        direction_consistency=0.75,
    )
    assert 0.0 <= f["orbit_fit_quality"] <= 1.0
    assert 0.0 <= f["hyperbolic_likelihood"] <= 1.0
    assert 0.0 <= f["eccentricity_placeholder"] <= 1.8
    assert f["inbound_outbound_placeholder"] in {"unknown", "possible_candidate", "strong_candidate"}
