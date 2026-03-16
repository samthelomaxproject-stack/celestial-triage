import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from celestial_triage.scoring.followup import build_followup_priority
from celestial_triage.scoring.interpretation import build_interpretation_summary
from celestial_triage.scoring.iso_review import build_iso_review_signal

DB_PATH = Path("celestial_triage.db")

st.set_page_config(page_title="Celestial Triage", layout="wide")
st.title("Celestial Triage Dashboard")

if not DB_PATH.exists():
    st.warning("Database not found. Run: init-db → seed-mock/ingest-jsonl → run-pipeline")
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
    review_state = st.selectbox("Review state", ["all", "new", "reviewing", "follow-up", "dismissed"])
    retention = st.selectbox("Retention tier", ["all", "hot", "warm", "cold", "disposable"])
    high_iso_only = st.checkbox("High ISO score only (>=0.7)", value=False)
    limit = st.slider("Top N", 10, 200, 50)

base_sql = """
SELECT c.candidate_id,
       c.review_status,
       ap.retention_tier,
       MAX(ds.score) as max_score,
       MAX(CASE WHEN ds.detector_name='iso_detector' THEN ds.score ELSE NULL END) as iso_score
FROM candidates c
LEFT JOIN detector_scores ds ON ds.candidate_id = c.candidate_id
LEFT JOIN archive_policies ap ON ap.candidate_id = c.candidate_id
GROUP BY c.candidate_id, c.review_status, ap.retention_tier
"""

rows = [dict(r) for r in conn.execute(base_sql).fetchall()]

if detector != "all":
    allowed = {
        r["candidate_id"]
        for r in conn.execute(
            "SELECT candidate_id FROM detector_scores WHERE detector_name=?",
            (detector,),
        ).fetchall()
    }
    rows = [r for r in rows if r["candidate_id"] in allowed]

if review_state != "all":
    rows = [r for r in rows if (r.get("review_status") or "new") == review_state]

if retention != "all":
    rows = [r for r in rows if (r.get("retention_tier") or "") == retention]

if high_iso_only:
    rows = [r for r in rows if float(r.get("iso_score") or 0.0) >= 0.7]

rows = sorted(rows, key=lambda r: float(r.get("max_score") or 0.0), reverse=True)[:limit]

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
        SELECT d.timestamp,d.broker_name,d.ra,d.dec,d.magnitude,d.magnitude_change,d.moving_flag,d.catalog_match_status
        FROM detections d JOIN candidate_detections cd ON d.detection_id=cd.detection_id
        WHERE cd.candidate_id=? ORDER BY d.timestamp ASC
        """,
        (candidate_id,),
    ).fetchall()
    retention_row = conn.execute("SELECT * FROM archive_policies WHERE candidate_id=?", (candidate_id,)).fetchone()

    with c1:
        st.markdown("### Candidate Console")
        st.json(dict(cand) if cand else {})
        if cand and cand.get("mock_archetype_label"):
            st.info(f"Demo-only mock archetype label: {cand['mock_archetype_label']}")

        if dets:
            by_source: dict[str, int] = {}
            for d in dets:
                k = d["broker_name"] or "unknown"
                by_source[k] = by_source.get(k, 0) + 1
            st.markdown("### Provenance")
            st.json({"detection_sources": by_source})

        st.markdown("### Timeline summary")
        if feats:
            st.write(f"First seen: `{feats['first_seen']}`")
            st.write(f"Last seen: `{feats['last_seen']}`")
            st.write(f"Detection count: `{feats['detection_count']}`")
            st.write(f"Detection span (h): `{float(feats['detection_span_hours']):.2f}`")

        if dets:
            df_dets = pd.DataFrame([dict(d) for d in dets])
            st.markdown("### Candidate timeline (magnitude)")
            try:
                df_dets["timestamp"] = pd.to_datetime(df_dets["timestamp"])
                chart_df = df_dets.set_index("timestamp")[["magnitude"]]
                st.line_chart(chart_df)
            except Exception:
                st.caption("Timeline chart unavailable for current data formatting")

        st.markdown("### Motion / Orbit summary")
        if feats:
            st.json(
                {
                    "motion_rate_deg_per_hour": feats["motion_rate_deg_per_hour"],
                    "motion_consistency": feats["motion_consistency_placeholder"],
                    "direction_consistency": feats["direction_consistency_placeholder"],
                    "heading_deg": feats["heading_deg_placeholder"],
                    "brightness_trend": feats["brightness_trend"],
                    "orbit_fit_quality": feats["orbit_fit_quality"],
                    "eccentricity_placeholder": feats["eccentricity_placeholder"],
                    "hyperbolic_likelihood": feats["hyperbolic_likelihood"],
                    "inbound_outbound": feats["inbound_outbound_placeholder"],
                }
            )

        st.markdown("### Detector scores (side-by-side)")
        pivot = {r["detector_name"]: float(r["score"]) for r in scores}
        st.dataframe([pivot], use_container_width=True)

        st.markdown("### Interpretation Summary")
        interpretation = build_interpretation_summary(dict(feats) if feats else {}, pivot)
        st.json(interpretation)

        st.markdown("### Detector conflicts")
        iso = float(pivot.get("iso_detector", 0.0))
        neo = float(pivot.get("neo_detector", 0.0))
        kbo = float(pivot.get("kbo_detector", 0.0))
        st.json(
            {
                "iso_vs_neo_delta": round(iso - neo, 3),
                "iso_vs_kbo_delta": round(iso - kbo, 3),
                "competing_high": [
                    name
                    for name, val in [("iso_detector", iso), ("neo_detector", neo), ("kbo_detector", kbo)]
                    if val >= 0.6
                ],
                "conflict_severity": interpretation.get("conflict_severity", "none"),
            }
        )

        st.markdown("### ISO Review")
        iso_review = build_iso_review_signal(dict(feats) if feats else {}, [dict(s) for s in scores])
        st.json(iso_review)

        st.markdown("### Follow-up Priority")
        score_map = {r["detector_name"]: float(r["score"]) for r in scores}
        followup = build_followup_priority(dict(feats) if feats else {}, score_map, (cand["review_status"] if cand else "new") or "new")
        st.metric("Priority", followup["priority"].upper(), delta=str(followup["priority_score"]))
        for reason in followup["reasons"]:
            st.write(f"- {reason}")

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

        st.markdown("### Detection history")
        st.dataframe(dets, use_container_width=True)

        st.markdown("### Retention")
        if retention_row:
            st.metric("Tier", retention_row["retention_tier"])
            st.caption(retention_row["rationale"])
        else:
            st.info("No retention decision yet. Run `assign-retention`.")

        st.markdown("### Export-ready summary")
        st.json(
            {
                "candidate_id": candidate_id,
                "review_state": (cand["review_status"] if cand else "new") if cand else "new",
                "tags": (cand["tags"] if cand else "") if cand else "",
                "notes": (cand["notes"] if cand else "") if cand else "",
                "iso_score": round(float(pivot.get("iso_detector", 0.0)), 3),
                "followup_priority": followup["priority"],
                "retention_tier": (retention_row["retention_tier"] if retention_row else ""),
                "first_seen": (feats["first_seen"] if feats else "") if feats else "",
                "last_seen": (feats["last_seen"] if feats else "") if feats else "",
                "detection_count": int((feats["detection_count"] if feats else 0) or 0),
            }
        )

    with c2:
        st.markdown("### Review workflow")
        current_state = (cand["review_status"] if cand else "new") or "new"
        state = st.selectbox("Review state", ["new", "reviewing", "follow-up", "dismissed"], index=["new", "reviewing", "follow-up", "dismissed"].index(current_state if current_state in ["new", "reviewing", "follow-up", "dismissed"] else "new"))
        tags = st.text_input("Tags (comma-separated)", value=(cand["tags"] if cand else "") or "")
        notes = st.text_area("Analyst notes", value=(cand["notes"] if cand else "") or "")
        if st.button("Save review"):
            conn.execute(
                "INSERT OR REPLACE INTO reviews(candidate_id, reviewed_flag, review_state, reviewed_by, reviewed_at, tags, analyst_notes) VALUES (?, ?, ?, 'analyst', datetime('now'), ?, ?)",
                (candidate_id, int(state != "new"), state, tags, notes),
            )
            conn.execute(
                "UPDATE candidates SET review_status=?, tags=?, notes=? WHERE candidate_id=?",
                (state, tags, notes, candidate_id),
            )
            conn.commit()
            st.success("Review saved")

conn.close()
