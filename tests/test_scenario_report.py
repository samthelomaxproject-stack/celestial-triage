from celestial_triage.models.entities import DetectorScore
from celestial_triage.scoring.evaluation import archetype_evaluation_report
from celestial_triage.storage.db import Database


def test_scenario_report_counts_and_alignment(tmp_path):
    db = Database(tmp_path / "eval.db")
    db.init()

    with db.conn() as c:
        c.execute(
            "INSERT INTO candidates(candidate_id,source_id,first_seen,last_seen,detection_count,average_ra,average_dec,current_status,review_status,mock_archetype_label,tags,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("c1", "s1", "2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00", 2, 0, 0, "active", "unreviewed", "neo_like", "", ""),
        )
        c.commit()

    db.insert_score(
        DetectorScore(
            detector_name="neo_detector",
            candidate_id="c1",
            score=0.9,
            score_band="high",
            reasons=["x"],
            version="v",
            created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )
    )

    rep = archetype_evaluation_report(db)
    assert rep["archetype_counts"]["neo_like"] == 1
    assert rep["alignment"]["aligned"] == 1
