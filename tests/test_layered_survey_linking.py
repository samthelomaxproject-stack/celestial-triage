from datetime import datetime, timezone

from celestial_triage.cli import _link_layered_survey_context_images
from celestial_triage.models.entities import NormalizedDetection
from celestial_triage.storage.db import Database


def _seed_candidate(db: Database, detection_id: str, source_id: str, ra: float, dec: float) -> str:
    det = NormalizedDetection(
        detection_id=detection_id,
        source_id=source_id,
        broker_name="lasair_api",
        timestamp=datetime.now(timezone.utc),
        ra=ra,
        dec=dec,
        magnitude=20.0,
        magnitude_change=0.0,
        moving_flag=True,
        class_label="unknown",
        class_confidence=0.2,
        catalog_match_status="no_match",
        raw_payload_reference="raw",
        ingest_time=datetime.now(timezone.utc),
        mock_archetype_label="",
    )
    db.insert_detection(det)
    db.rebuild_candidates_from_detections()
    return db.get_candidate_id_for_source(source_id) or ""


def test_layered_survey_images_link_and_dedupe(monkeypatch, tmp_path):
    db = Database(tmp_path / "ct.db")
    db.init()
    cid = _seed_candidate(db, "d1", "S1", 10.0, 20.0)
    assert cid

    def fake_layered(candidate_id, source_id, ra, dec, existing_kinds=None):
        existing_kinds = existing_kinds or set()
        if "survey_context_panstarrs" in existing_kinds:
            return {"candidate_id": candidate_id, "source_id": source_id, "panstarrs": None, "skyview": None}
        return {
            "candidate_id": candidate_id,
            "source_id": source_id,
            "panstarrs": {
                "remote_url": "https://ps1images.stsci.edu/cgi-bin/fitscut.cgi?ra=10&dec=20&size=240&format=png",
                "local_path": str(tmp_path / "image_previews" / cid / "survey_context_panstarrs.png"),
                "kind": "survey_context_panstarrs",
            },
            "skyview": None,
        }

    monkeypatch.setattr("celestial_triage.cli.ensure_layered_survey_images", fake_layered)

    summary1 = _link_layered_survey_context_images(db)
    summary2 = _link_layered_survey_context_images(db)

    imgs = db.get_images_for_candidate(cid)
    pan = [i for i in imgs if i["kind"] == "survey_context_panstarrs"]
    assert len(pan) == 1
    assert summary1["panstarrs_context_added"] >= 1
    assert summary2["panstarrs_context_added"] == 0
