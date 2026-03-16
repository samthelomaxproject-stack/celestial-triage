from datetime import datetime, timedelta, timezone

from celestial_triage.models.entities import NormalizedDetection
from celestial_triage.storage.db import Database


def test_candidate_linking_rollup(tmp_path):
    db = Database(tmp_path / "link.db")
    db.init()

    base_t = datetime.now(timezone.utc)
    for i in range(3):
        d = NormalizedDetection(
            detection_id=f"d{i}",
            source_id="SRC-TEST",
            broker_name="mock",
            timestamp=base_t + timedelta(hours=i),
            ra=10.0 + i,
            dec=20.0,
            magnitude=19.5 - (i * 0.1),
            magnitude_change=0.1,
            moving_flag=True,
            class_label="unknown",
            class_confidence=0.3,
            catalog_match_status="poor_match",
            raw_payload_reference=f"r{i}",
            ingest_time=base_t,
        )
        db.insert_detection(d)

    count = db.rebuild_candidates_from_detections()
    assert count == 1

    cids = db.list_candidate_ids()
    assert len(cids) == 1
    c = db.get_candidate_with_features(cids[0])
    assert c["detection_count"] == 3
    assert float(c["average_ra"]) == 11.0
