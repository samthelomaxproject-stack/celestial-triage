from celestial_triage.storage.db import Database


def test_orbit_fields_persist_in_shared_features(tmp_path):
    db = Database(tmp_path / "orbit.db")
    db.init()

    with db.conn() as c:
        c.execute(
            "INSERT INTO candidates(candidate_id,source_id,first_seen,last_seen,detection_count,average_ra,average_dec,current_status,review_status,tags,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("c1", "s1", "2026-01-01T00:00:00+00:00", "2026-01-01T02:00:00+00:00", 3, 10.0, 20.0, "active", "unreviewed", "", ""),
        )
        c.commit()

    db.upsert_shared_features(
        "c1",
        {
            "detection_count": 3,
            "first_seen": "2026-01-01T00:00:00+00:00",
            "last_seen": "2026-01-01T02:00:00+00:00",
            "detection_span_hours": 2.0,
            "avg_magnitude": 19.4,
            "mag_delta_abs": 0.7,
            "brightness_trend": -0.7,
            "moving_fraction": 1.0,
            "motion_rate_deg_per_hour": 0.8,
            "motion_consistency_placeholder": 0.9,
            "direction_consistency_placeholder": 0.85,
            "heading_deg_placeholder": 33.0,
            "poor_catalog_fraction": 0.8,
            "avg_class_confidence": 0.2,
            "angular_motion_placeholder": 1.6,
            "orbit_fit_quality": 0.7,
            "eccentricity_placeholder": 1.1,
            "hyperbolic_likelihood": 0.4,
            "inbound_outbound_placeholder": "inbound_or_outbound_candidate",
            "orbit_fit_placeholder": 0.6,
            "hyperbolic_likelihood_placeholder": 0.4,
            "anomaly_index_placeholder": 0.5,
        },
    )

    row = db.get_candidate_with_features("c1")["features"]
    assert row["orbit_fit_quality"] == 0.7
    assert row["eccentricity_placeholder"] == 1.1
    assert row["hyperbolic_likelihood"] == 0.4
