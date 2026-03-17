from datetime import datetime, timezone

from celestial_triage.models.entities import NormalizedDetection
from celestial_triage.storage.db import Database
from celestial_triage.ui.sky_map import nearest_point, prepare_candidate_sky_points


def _det(did: str, sid: str, ra, dec):
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
        catalog_match_status="no_match",
        raw_payload_reference=f"raw-{did}",
        ingest_time=datetime.now(timezone.utc),
        mock_archetype_label="",
    )


def test_prepare_candidate_sky_points_extracts_positions(tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()
    db.insert_detection(_det("d1", "S1", 10.1, -2.3))
    db.insert_detection(_det("d2", "S2", 11.1, -1.3))
    db.rebuild_candidates_from_detections()

    points = prepare_candidate_sky_points(db)
    assert len(points) == 2
    assert all("candidate_id" in p and "ra" in p and "dec" in p for p in points)


def test_prepare_candidate_sky_points_handles_missing_coords(tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()
    db.insert_detection(_det("d1", "S1", 10.0, -2.3))
    db.rebuild_candidates_from_detections()

    cid = db.get_candidate_id_for_source("S1")
    with db.conn() as c:
        c.execute("UPDATE candidates SET average_ra='nan' WHERE candidate_id=?", (cid,))
        c.commit()

    points = prepare_candidate_sky_points(db)
    assert points == []


def test_nearest_point_selection_helper():
    points = [
        {"candidate_id": "c1", "_px": 10.0, "_py": 10.0},
        {"candidate_id": "c2", "_px": 100.0, "_py": 100.0},
    ]
    p = nearest_point(points, 12.0, 11.0, max_px_dist=10.0)
    assert p is not None and p["candidate_id"] == "c1"
    p2 = nearest_point(points, 300.0, 300.0, max_px_dist=10.0)
    assert p2 is None
