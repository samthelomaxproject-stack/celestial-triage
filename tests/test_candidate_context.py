from datetime import datetime, timezone

from celestial_triage.context import build_candidate_context
from celestial_triage.models.entities import NormalizedDetection
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
