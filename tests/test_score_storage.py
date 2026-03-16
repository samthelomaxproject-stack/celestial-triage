from pathlib import Path
from datetime import datetime, timezone

from celestial_triage.models.entities import DetectorScore
from celestial_triage.storage.db import Database


def test_score_storage(tmp_path: Path):
    db_file = tmp_path / "t.db"
    db = Database(db_file)
    db.init()

    # Minimal candidate row to attach score
    with db.conn() as c:
        c.execute(
            "INSERT INTO candidates(candidate_id,source_id,first_seen,last_seen,detection_count,average_ra,average_dec,current_status,review_status,tags,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("c1", "s1", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", 1, 0.0, 0.0, "active", "unreviewed", "", ""),
        )
        c.commit()

    db.insert_score(
        DetectorScore(
            detector_name="neo_detector",
            candidate_id="c1",
            score=0.8,
            score_band="high",
            reasons=["test"],
            version="v0",
            created_at=datetime.now(timezone.utc),
        )
    )
    top = db.top_candidates(limit=5)
    assert top
    assert top[0]["candidate_id"] == "c1"
