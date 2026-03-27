from datetime import datetime, timezone

from celestial_triage.context import build_candidate_context
from celestial_triage.models.entities import DetectorScore, NormalizedDetection
from celestial_triage.storage.db import Database


def _det(did: str, sid: str, ra: float, dec: float, match: str = "no_match") -> NormalizedDetection:
    return NormalizedDetection(
        detection_id=did,
        source_id=sid,
        broker_name="lasair_api",
        timestamp=datetime.now(timezone.utc),
        ra=ra,
        dec=dec,
        magnitude=20.0,
        magnitude_change=0.0,
        moving_flag=True,
        class_label="unknown",
        class_confidence=0.3,
        catalog_match_status=match,
        raw_payload_reference=f"raw-{did}",
        ingest_time=datetime.now(timezone.utc),
        mock_archetype_label="",
    )


def test_context_summary_structure_and_values(tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()
    db.insert_detection(_det("d1", "S1", 10.0, 10.0, "no_match"))
    db.insert_detection(_det("d2", "S2", 10.01, 10.01, "matched"))
    db.rebuild_candidates_from_detections()

    cid = db.get_candidate_id_for_source("S1")
    ctx = build_candidate_context(db, cid)
    # Required structured fields
    assert ctx["candidate_id"] == cid
    assert "ra" in ctx and "dec" in ctx
    assert "context_status" in ctx
    assert "host_context_note" in ctx
    assert "crowdedness_note" in ctx
    assert "catalog_context_note" in ctx
    assert "provenance_note" in ctx
    assert "concise_explanation" in ctx
    # Backward-compatible fields still present
    assert "nearest_object_summary" in ctx
    assert "host_hint" in ctx
    assert "field_density" in ctx
    assert "context_interpretation" in ctx


def test_context_handles_missing_candidate_gracefully(tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()
    ctx = build_candidate_context(db, "missing")
    assert ctx["context_status"] == "limited"
    assert ctx["host_context_note"] == "No context available"
    assert "Insufficient" in ctx["concise_explanation"]


def test_context_handles_invalid_coordinates(tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()
    db.insert_detection(_det("d1", "S1", 10.0, 10.0, "no_match"))
    db.rebuild_candidates_from_detections()
    cid = db.get_candidate_id_for_source("S1")
    with db.conn() as c:
        c.execute("UPDATE candidates SET average_ra='nan', average_dec='nan' WHERE candidate_id=?", (cid,))
        c.commit()
    ctx = build_candidate_context(db, cid)
    # non-finite values still produce degraded but safe output
    assert "candidate_id" in ctx
    assert "concise_explanation" in ctx


def test_context_includes_plate_solve_provenance_when_linked(tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()
    db.insert_detection(_det("d1", "S1", 10.0, 10.0, "matched"))
    db.rebuild_candidates_from_detections()
    cid = db.get_candidate_id_for_source("S1")

    db.insert_plate_solve(
        solve_id="solve_test_1",
        image_path="/tmp/test.png",
        status="success",
        ra_center=10.0,
        dec_center=10.0,
        field_width_deg=0.1,
        field_height_deg=0.1,
        orientation_deg=1.0,
        pixel_scale_arcsec=1.5,
        backend="astrometry.net",
        job_id="123",
        error_message=None,
        metadata_json="{}",
        candidate_id=cid,
    )

    ctx = build_candidate_context(db, cid)
    assert ctx["plate_solve_count"] == 1
    assert ctx["latest_plate_solve_backend"] == "astrometry.net"
    assert ctx["latest_plate_solve_status"] == "success"
    assert ctx["latest_plate_solve_timestamp"] is not None
    assert "plate_solve:1" in ctx["provenance_note"]


def test_context_handles_no_plate_solve_rows(tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()
    db.insert_detection(_det("d1", "S1", 10.0, 10.0, "matched"))
    db.rebuild_candidates_from_detections()
    cid = db.get_candidate_id_for_source("S1")

    ctx = build_candidate_context(db, cid)
    assert ctx["plate_solve_count"] == 0
    assert ctx["latest_plate_solve_backend"] is None
    assert ctx["latest_plate_solve_status"] is None
    assert ctx["latest_plate_solve_timestamp"] is None


def test_context_flags_anomaly_with_temporal_and_signal(tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()
    db.insert_detection(_det("d1", "S1", 10.0, 10.0, "no_match"))
    db.rebuild_candidates_from_detections()
    cid = db.get_candidate_id_for_source("S1")

    det = db.get_detections_for_candidate(cid)[0]
    db.upsert_image_asset(
        detection_id=det["detection_id"],
        source_id="S1",
        broker_name="lasair_api",
        kind="science",
        remote_url="https://example.org/science.fits",
    )
    db.relink_image_assets_to_candidates()

    db.insert_score(
        DetectorScore(
            detector_name="unknown_mover_detector",
            candidate_id=cid,
            score=0.85,
            score_band="high",
            reasons=["test"],
            version="test",
            created_at=datetime.now(timezone.utc),
        )
    )

    ctx = build_candidate_context(db, cid)
    assert ctx["anomaly_flag"] is True
    assert "catalog" in ctx["anomaly_reason"] or "unknown_mover_detector" in ctx["anomaly_reason"]


def test_context_not_anomaly_without_temporal_images(tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()
    db.insert_detection(_det("d1", "S1", 10.0, 10.0, "no_match"))
    db.rebuild_candidates_from_detections()
    cid = db.get_candidate_id_for_source("S1")

    # signal exists, but no temporal image means not anomaly per definition
    db.insert_score(
        DetectorScore(
            detector_name="unknown_mover_detector",
            candidate_id=cid,
            score=0.9,
            score_band="high",
            reasons=["test"],
            version="test",
            created_at=datetime.now(timezone.utc),
        )
    )

    ctx = build_candidate_context(db, cid)
    assert ctx["anomaly_flag"] is False
    assert "No broker temporal images" in ctx["anomaly_reason"]
