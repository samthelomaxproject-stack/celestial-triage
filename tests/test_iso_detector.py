from celestial_triage.detectors.iso_detector import evaluate


def test_iso_detector_uses_new_orbit_motion_fields():
    high = {
        "hyperbolic_likelihood": 0.9,
        "eccentricity_placeholder": 1.2,
        "poor_catalog_fraction": 0.8,
        "detection_count": 5,
        "motion_consistency_placeholder": 0.8,
        "direction_consistency_placeholder": 0.8,
    }
    low = {
        "hyperbolic_likelihood": 0.1,
        "eccentricity_placeholder": 0.4,
        "poor_catalog_fraction": 0.1,
        "detection_count": 1,
        "motion_consistency_placeholder": 0.2,
        "direction_consistency_placeholder": 0.2,
    }

    hs, _ = evaluate(high)
    ls, _ = evaluate(low)
    assert hs > ls
