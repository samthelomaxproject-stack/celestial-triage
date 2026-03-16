import json
import sqlite3
from pathlib import Path

import streamlit as st

DB_PATH = Path("celestial_triage.db")

st.set_page_config(page_title="Celestial Triage", layout="wide")
st.title("Celestial Triage Dashboard")

if not DB_PATH.exists():
    st.warning("Database not found. Run: init-db → seed-mock → run-pipeline")
    st.stop()

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

score_count = conn.execute("SELECT COUNT(*) FROM detector_scores").fetchone()[0]
if score_count == 0:
    st.info("No detector scores found yet. Run `python -m celestial_triage.cli run-pipeline`.")
    conn.close()
    st.stop()

with st.sidebar:
    st.header("Filters")
    detector = st.selectbox(
        "Detector",
        [
            "all",
            "satellite_detector",
            "neo_detector",
            "unknown_mover_detector",
            "kbo_detector",
            "iso_detector",
            "deep_anomaly_detector",
        ],
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

if not rows:
    st.info("No candidates match current filters.")
    conn.close()
    st.stop()

candidate_id = st.selectbox("Select candidate", [r["candidate_id"] for r in rows])

if candidate_id:
    c1, c2 = st.columns([2, 1])

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

    with c1:
        st.markdown("### Candidate")
        st.json(dict(cand) if cand else {})
        if cand and cand.get("mock_archetype_label"):
            st.info(f"Demo-only mock archetype label: {cand['mock_archetype_label']}")

        st.markdown("### Retention tier")
        if retention:
            st.metric("Tier", retention["retention_tier"])
            st.caption(retention["rationale"])
        else:
            st.info("No retention decision yet. Run `assign-retention`.")

        st.markdown("### Motion features")
        if feats:
            st.json(
                {
                    "detection_count": feats["detection_count"],
                    "first_seen": feats["first_seen"],
                    "last_seen": feats["last_seen"],
                    "detection_span_hours": feats["detection_span_hours"],
                    "motion_rate_deg_per_hour": feats["motion_rate_deg_per_hour"],
                    "motion_consistency_placeholder": feats["motion_consistency_placeholder"],
                    "direction_consistency_placeholder": feats["direction_consistency_placeholder"],
                    "heading_deg_placeholder": feats["heading_deg_placeholder"],
                }
            )

        st.markdown("### Orbit scaffold features")
        if feats:
            st.json(
                {
                    "orbit_fit_quality": feats["orbit_fit_quality"],
                    "eccentricity_placeholder": feats["eccentricity_placeholder"],
                    "hyperbolic_likelihood": feats["hyperbolic_likelihood"],
                    "inbound_outbound_placeholder": feats["inbound_outbound_placeholder"],
                }
            )

        st.markdown("### Shared features (full)")
        st.json(dict(feats) if feats else {})

        st.markdown("### Detector scores (side-by-side)")
        pivot = {r["detector_name"]: float(r["score"]) for r in scores}
        st.dataframe([pivot], use_container_width=True)

        st.markdown("### Score reasons")
        for r in scores:
            with st.expander(f"{r['detector_name']} • {r['score']:.3f} ({r['score_band']})"):
                try:
                    reasons = json.loads(r["reasons_json"])
                except json.JSONDecodeError:
                    reasons = [r["reasons_json"]]
                for reason in reasons:
                    st.write(f"- {reason}")
                st.caption(f"Scored at {r['created_at']}")

        st.markdown("### Detection timeline summary")
        if dets:
            first_ts = dets[0]["timestamp"]
            last_ts = dets[-1]["timestamp"]
            st.write(f"First seen: `{first_ts}`")
            st.write(f"Last seen: `{last_ts}`")
            st.write(f"Sequence length: `{len(dets)}` detections")
        st.markdown("### Detection history")
        st.dataframe(dets, use_container_width=True)

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
