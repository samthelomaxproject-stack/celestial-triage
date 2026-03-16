from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

from celestial_triage.cli import cmd_bundle_cases
from celestial_triage.models.entities import DetectorScore
from celestial_triage.storage.db import Database


def test_bundle_cases_creates_summary_and_details(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = Database(Path("celestial_triage.db"))
    db.init()

    with db.conn() as c:
        c.execute(
            "INSERT INTO candidates(candidate_id,source_id,first_seen,last_seen,detection_count,average_ra,average_dec,current_status,review_status,mock_archetype_label,tags,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("c1", "s1", "2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00", 2, 0, 0, "active", "follow-up", "", "tag1", "note1"),
        )
        c.execute(
            "INSERT INTO detections(detection_id,source_id,broker_name,timestamp,ra,dec,magnitude,magnitude_change,moving_flag,class_label,class_confidence,catalog_match_status,raw_payload_reference,ingest_time,mock_archetype_label) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("d1", "s1", "external_jsonl", "2026-01-01T00:00:00+00:00", 10.0, 20.0, 19.0, 0.1, 1, "unknown", 0.3, "poor_match", "r1", "2026-01-01T00:00:00+00:00", ""),
        )
        c.execute("INSERT INTO candidate_detections(candidate_id,detection_id) VALUES (?,?)", ("c1", "d1"))
        c.execute(
            "INSERT INTO shared_features(candidate_id,detection_count,first_seen,last_seen,detection_span_hours,avg_magnitude,mag_delta_abs,brightness_trend,moving_fraction,motion_rate_deg_per_hour,motion_consistency_placeholder,direction_consistency_placeholder,heading_deg_placeholder,heading_change_consistency,path_smoothness_placeholder,trajectory_quality,poor_catalog_fraction,avg_class_confidence,angular_motion_placeholder,orbit_fit_quality,eccentricity_placeholder,hyperbolic_likelihood,inbound_outbound_placeholder,orbit_fit_placeholder,hyperbolic_likelihood_placeholder,anomaly_index_placeholder,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "c1", 2, "2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00", 1.0, 19.0, 0.1, 0.1, 1.0,
                1.0, 0.8, 0.8, 15.0, 0.75, 0.7, 0.78, 0.7, 0.3, 1.0, 0.7, 1.2, 0.8, "possible_candidate", 0.4, 0.5, 0.5,
                "2026-01-01T01:00:00+00:00",
            ),
        )
        c.execute(
            "INSERT INTO archive_policies(candidate_id,retention_tier,keep_raw_payload,keep_derived_products,expiration_date,rationale,decided_at) VALUES (?,?,?,?,?,?,?)",
            ("c1", "hot", 1, 1, None, "r", "2026-01-01T01:10:00+00:00"),
        )
        c.commit()

    db.insert_score(DetectorScore("iso_detector", "c1", 0.9, "high", ["x"], "v", datetime.now(timezone.utc)))

    out_dir = tmp_path / "bundle"
    args = Namespace(
        output_dir=str(out_dir),
        review_state="follow-up",
        followup_priority=None,
        detector=None,
        high_iso=False,
        tagged_only=False,
        broker=None,
        include_details=True,
    )

    cmd_bundle_cases(args)

    assert (out_dir / "summary.json").exists()
    assert (out_dir / "summary.md").exists()
    assert (out_dir / "candidates" / "c1.json").exists()
