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
    assert "nearest_object_summary" in ctx
    assert "host_hint" in ctx
    assert "field_density" in ctx
    assert "context_interpretation" in ctx
    assert ctx["catalog_match_status"] in ("no_match", "matched", "unknown")


def test_context_handles_missing_candidate_gracefully(tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()
    ctx = build_candidate_context(db, "missing")
    assert ctx["host_hint"] == "unknown"
    assert "Insufficient" in ctx["context_interpretation"]
