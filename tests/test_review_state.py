from celestial_triage.storage.db import Database


def test_review_state_persistence(tmp_path):
    db = Database(tmp_path / "review.db")
    db.init()

    with db.conn() as c:
        c.execute(
            "INSERT INTO candidates(candidate_id,source_id,first_seen,last_seen,detection_count,average_ra,average_dec,current_status,review_status,mock_archetype_label,tags,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("c1", "s1", "2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00", 2, 0, 0, "active", "new", "", "", ""),
        )
        c.commit()

    db.upsert_review("c1", "follow-up", tags="iso,priority", notes="needs follow-up")

    with db.conn() as c:
        r = c.execute("SELECT review_state,tags,analyst_notes FROM reviews WHERE candidate_id='c1'").fetchone()
        cnd = c.execute("SELECT review_status,tags,notes FROM candidates WHERE candidate_id='c1'").fetchone()

    assert r["review_state"] == "follow-up"
    assert "iso" in r["tags"]
    assert cnd["review_status"] == "follow-up"
