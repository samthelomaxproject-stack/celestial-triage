import sqlite3
from pathlib import Path

import streamlit as st

DB_PATH = Path("celestial_triage.db")

st.set_page_config(page_title="Celestial Triage", layout="wide")
st.title("Celestial Triage Dashboard")

if not DB_PATH.exists():
    st.warning("Database not found. Run CLI seed + pipeline first.")
    st.stop()

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

with st.sidebar:
    st.header("Filters")
    detector = st.selectbox(
        "Detector",
        ["all", "satellite_detector", "neo_detector", "unknown_mover_detector", "kbo_detector", "iso_detector", "deep_anomaly_detector"],
    )
    band = st.selectbox("Score band", ["all", "high", "medium", "low"])
    limit = st.slider("Top N", 10, 200, 50)

filters = []
vals: list = []
if detector != "all":
    filters.append("detector_name=?")
    vals.append(detector)
if band != "all":
    filters.append("score_band=?")
    vals.append(band)
where = f"WHERE {' AND '.join(filters)}" if filters else ""

q = f"""
SELECT candidate_id, MAX(score) max_score
FROM detector_scores
{where}
GROUP BY candidate_id
ORDER BY max_score DESC
LIMIT ?
"""
vals.append(limit)
rows = conn.execute(q, vals).fetchall()

st.subheader("Top-ranked candidates")
st.dataframe(rows, use_container_width=True)

candidate_id = st.selectbox("Select candidate", [r["candidate_id"] for r in rows] if rows else [])

if candidate_id:
    c1, c2 = st.columns([2, 1])
    with c1:
        cand = conn.execute("SELECT * FROM candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        feats = conn.execute("SELECT * FROM shared_features WHERE candidate_id=?", (candidate_id,)).fetchone()
        scores = conn.execute(
            "SELECT detector_name, score, score_band, reasons_json, created_at FROM detector_scores WHERE candidate_id=? ORDER BY score DESC",
            (candidate_id,),
        ).fetchall()
        dets = conn.execute(
            """
            SELECT d.timestamp,d.ra,d.dec,d.magnitude,d.magnitude_change,d.moving_flag,d.catalog_match_status
            FROM detections d JOIN candidate_detections cd ON d.detection_id=cd.detection_id
            WHERE cd.candidate_id=? ORDER BY d.timestamp ASC
            """,
            (candidate_id,),
        ).fetchall()
        retention = conn.execute("SELECT * FROM archive_policies WHERE candidate_id=?", (candidate_id,)).fetchone()

        st.markdown("### Candidate")
        st.json(dict(cand) if cand else {})
        st.markdown("### Shared features")
        st.json(dict(feats) if feats else {})
        st.markdown("### Detector scores")
        st.dataframe(scores, use_container_width=True)
        st.markdown("### Detection history")
        st.dataframe(dets, use_container_width=True)
        st.markdown("### Retention")
        st.json(dict(retention) if retention else {})

    with c2:
        st.markdown("### Review actions")
        reviewed = st.checkbox("Mark reviewed")
        tags = st.text_input("Tags (comma-separated)")
        notes = st.text_area("Analyst notes")
        if st.button("Save review"):
            conn.execute(
                "INSERT OR REPLACE INTO reviews(candidate_id, reviewed_flag, reviewed_by, reviewed_at, tags, analyst_notes) VALUES (?, ?, 'analyst', datetime('now'), ?, ?)",
                (candidate_id, int(reviewed), tags, notes),
            )
            conn.execute(
                "UPDATE candidates SET review_status=?, tags=?, notes=? WHERE candidate_id=?",
                ("reviewed" if reviewed else "unreviewed", tags, notes, candidate_id),
            )
            conn.commit()
            st.success("Review saved")

conn.close()
