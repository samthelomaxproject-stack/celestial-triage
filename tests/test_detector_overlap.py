from datetime import datetime, timezone

from celestial_triage.models.entities import DetectorScore
from celestial_triage.scoring.evaluation import archetype_evaluation_report
from celestial_triage.storage.db import Database


def test_scenario_report_tracks_iso_overlap_metrics(tmp_path):
    db = Database(tmp_path / "overlap.db")
    db.init()

    with db.conn() as c:
        c.execute(
            "INSERT INTO candidates(candidate_id,source_id,first_seen,last_seen,detection_count,average_ra,average_dec,current_status,review_status,mock_archetype_label,tags,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "c_iso",
                "s_iso",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T02:00:00+00:00",
                3,
                10.0,
                20.0,
                "active",
                "unreviewed",
                "inbound_interstellar_like",
                "",
                "",
            ),
        )
        c.commit()

    now = datetime.now(timezone.utc)
    db.insert_score(DetectorScore("iso_detector", "c_iso", 0.8, "high", ["iso"], "v", now))
    db.insert_score(DetectorScore("neo_detector", "c_iso", 0.7, "high", ["neo"], "v", now))
    db.insert_score(DetectorScore("kbo_detector", "c_iso", 0.65, "high", ["kbo"], "v", now))

    rep = archetype_evaluation_report(db, top_iso_limit=5)
    assert rep["iso_overlap"]["iso_vs_neo_high"] >= 1
    assert rep["iso_overlap"]["iso_vs_kbo_high"] >= 1
    assert len(rep["top_iso_candidates"]) >= 1
