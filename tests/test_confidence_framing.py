from celestial_triage.scoring.interpretation import build_interpretation_summary


def test_confidence_stronger_with_clear_gap_and_evidence():
    base_features = {
        "detection_count": 6,
        "orbit_fit_quality": 0.8,
        "poor_catalog_fraction": 0.1,
    }
    weak = build_interpretation_summary(base_features, {"iso_detector": 0.55, "neo_detector": 0.52, "kbo_detector": 0.48})
    strong = build_interpretation_summary(base_features, {"iso_detector": 0.9, "neo_detector": 0.45, "kbo_detector": 0.3})

    order = {"weak": 1, "moderate": 2, "strong": 3}
    assert order[strong["confidence"]] >= order[weak["confidence"]]
