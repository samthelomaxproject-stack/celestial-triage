from typing import Any

from celestial_triage.storage.db import Database

EXPECTED_PRIMARY_DETECTOR = {
    "fast_satellite_like": "satellite_detector",
    "neo_like": "neo_detector",
    "slow_persistent_kbo_like": "kbo_detector",
    "inbound_interstellar_like": "iso_detector",
    "outbound_hyperbolic_like": "iso_detector",
    "ambiguous_anomaly_like": "deep_anomaly_detector",
}


def archetype_evaluation_report(db: Database) -> dict[str, Any]:
    with db.conn() as c:
        cand_rows = c.execute("SELECT candidate_id, mock_archetype_label FROM candidates").fetchall()

    archetype_counts: dict[str, int] = {}
    top_detector_by_archetype: dict[str, dict[str, int]] = {}
    alignment = {"aligned": 0, "conflict": 0}

    for row in cand_rows:
        cid = row["candidate_id"]
        archetype = row["mock_archetype_label"] or "unknown"
        archetype_counts[archetype] = archetype_counts.get(archetype, 0) + 1

        scores = db.get_latest_scores(cid)
        if not scores:
            continue
        top = sorted(scores, key=lambda s: float(s["score"]), reverse=True)[0]
        det = top["detector_name"]

        if archetype not in top_detector_by_archetype:
            top_detector_by_archetype[archetype] = {}
        top_detector_by_archetype[archetype][det] = top_detector_by_archetype[archetype].get(det, 0) + 1

        expected = EXPECTED_PRIMARY_DETECTOR.get(archetype)
        if expected and det == expected:
            alignment["aligned"] += 1
        elif expected:
            alignment["conflict"] += 1

    return {
        "archetype_counts": archetype_counts,
        "top_detector_by_archetype": top_detector_by_archetype,
        "alignment": alignment,
    }
