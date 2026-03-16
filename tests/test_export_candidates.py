import json
from datetime import datetime, timezone
from pathlib import Path

from celestial_triage.cli import build_export_rows
from celestial_triage.models.entities import DetectorScore
from celestial_triage.storage.db import Database


def test_export_filters_and_fields(tmp_path: Path):
    db = Database(tmp_path / "export.db")
    db.init()

    with db.conn() as c:
        c.execute(
            "INSERT INTO candidates(candidate_id,source_id,first_seen,last_seen,detection_count,average_ra,average_dec,current_status,review_status,mock_archetype_label,tags,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("c1", "s1", "2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00", 2, 0, 0, "active", "follow-up", "", "iso,priority", "note"),
        )
        c.execute(
            "INSERT INTO detections(detection_id,source_id,broker_name,timestamp,ra,dec,magnitude,magnitude_change,moving_flag,class_label,class_confidence,catalog_match_status,raw_payload_reference,ingest_time,mock_archetype_label) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("d1", "s1", "external_jsonl", "2026-01-01T00:00:00+00:00", 10.0, 20.0, 19.2, 0.2, 1, "unknown", 0.3, "poor_match", "r1", "2026-01-01T00:00:00+00:00", ""),
        )
        c.execute("INSERT INTO candidate_detections(candidate_id,detection_id) VALUES (?,?)", ("c1", "d1"))
        c.execute(
            "INSERT INTO shared_features(candidate_id,detection_count,first_seen,last_seen,detection_span_hours,avg_magnitude,mag_delta_abs,brightness_trend,moving_fraction,motion_rate_deg_per_hour,motion_consistency_placeholder,direction_consistency_placeholder,heading_deg_placeholder,poor_catalog_fraction,avg_class_confidence,angular_motion_placeholder,orbit_fit_quality,eccentricity_placeholder,hyperbolic_likelihood,inbound_outbound_placeholder,orbit_fit_placeholder,hyperbolic_likelihood_placeholder,anomaly_index_placeholder,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "c1",
                2,
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T01:00:00+00:00",
                1.0,
                19.2,
                0.2,
                0.2,
                1.0,
                1.1,
                0.7,
                0.7,
                20.0,
                0.8,
                0.2,
                1.0,
                0.6,
                1.2,
                0.75,
                "possible_candidate",
                0.4,
                0.5,
                0.5,
                "2026-01-01T01:01:00+00:00",
            ),
        )
        c.execute(
            "INSERT INTO archive_policies(candidate_id,retention_tier,keep_raw_payload,keep_derived_products,expiration_date,rationale,decided_at) VALUES (?,?,?,?,?,?,?)",
            ("c1", "hot", 1, 1, None, "test", "2026-01-01T01:05:00+00:00"),
        )
        c.commit()

    now = datetime.now(timezone.utc)
    db.insert_score(DetectorScore("iso_detector", "c1", 0.9, "high", ["iso"], "v", now))

    rows = build_export_rows(db, review_state="follow-up", high_iso_only=True, tagged_only=True, broker="external_jsonl")
    assert len(rows) == 1
    r = rows[0]
    assert r["candidate_id"] == "c1"
    assert r["review_state"] == "follow-up"
    assert r["retention_tier"] == "hot"
    assert r["iso_score"] >= 0.7
    assert "external_jsonl" in r["provenance_summary"]
