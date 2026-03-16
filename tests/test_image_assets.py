from datetime import datetime, timezone

from celestial_triage.ingest.image_assets import extract_image_assets_from_payload
from celestial_triage.models.entities import NormalizedDetection
from celestial_triage.storage.db import Database


def test_extract_image_assets_from_payload_detects_common_cutouts():
    payload = {
        "cutouts": {
            "science": {"url": "https://example.org/science.png"},
            "reference": {"url": "https://example.org/reference.png"},
            "difference": {"url": "https://example.org/difference.png"},
        }
    }
    items = extract_image_assets_from_payload(payload)
    kinds = {i["kind"] for i in items}
    assert {"science", "reference", "difference"}.issubset(kinds)


def test_image_asset_persistence_and_candidate_link(tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()

    det = NormalizedDetection(
        detection_id="d1",
        source_id="S1",
        broker_name="lasair_api",
        timestamp=datetime.now(timezone.utc),
        ra=10.0,
        dec=-5.0,
        magnitude=20.0,
        magnitude_change=0.0,
        moving_flag=True,
        class_label="unknown",
        class_confidence=0.1,
        catalog_match_status="no_match",
        raw_payload_reference="raw-1",
        ingest_time=datetime.now(timezone.utc),
        mock_archetype_label="",
    )
    db.insert_detection(det)
    db.rebuild_candidates_from_detections()

    db.upsert_image_asset(
        detection_id="d1",
        source_id="S1",
        broker_name="lasair_api",
        kind="science",
        remote_url="https://example.org/science.png",
    )
    db.relink_image_assets_to_candidates()

    cid = db.list_candidate_ids()[0]
    images = db.get_images_for_candidate(cid)
    assert len(images) == 1
    assert images[0]["kind"] == "science"
    assert images[0]["remote_url"] == "https://example.org/science.png"
