from datetime import datetime, timedelta, timezone

from celestial_triage.models.entities import NormalizedDetection
from celestial_triage.storage.db import Database


def test_candidate_association_filters_implausible_jumps(tmp_path):
    db = Database(tmp_path / "assoc.db")
    db.init()

    t0 = datetime.now(timezone.utc)
    # coherent progression
    rows = [
        (10.0, 10.0),
        (10.2, 10.1),
        (10.4, 10.2),
        # implausible jump
        (40.0, -30.0),
        # coherent continuation from prior coherent branch
        (10.6, 10.3),
        (10.8, 10.4),
    ]

    for i, (ra, dec) in enumerate(rows):
        d = NormalizedDetection(
            detection_id=f"d{i}",
            source_id="SRC-A",
            broker_name="mock",
            timestamp=t0 + timedelta(minutes=10 * i),
            ra=ra,
            dec=dec,
            magnitude=19.0,
            magnitude_change=0.1,
            moving_flag=True,
            class_label="unknown",
            class_confidence=0.3,
            catalog_match_status="poor_match",
            raw_payload_reference=f"r{i}",
            ingest_time=t0,
        )
        db.insert_detection(d)

    cid = db.upsert_candidate_from_source("SRC-A")
    linked = db.get_detections_for_candidate(cid)

    assert len(linked) < len(rows)
    assert len(linked) >= 4
