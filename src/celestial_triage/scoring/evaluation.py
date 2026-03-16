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


def archetype_evaluation_report(db: Database, top_iso_limit: int = 10) -> dict[str, Any]:
    with db.conn() as c:
        cand_rows = c.execute("SELECT candidate_id, mock_archetype_label FROM candidates").fetchall()

    archetype_counts: dict[str, int] = {}
    top_detector_by_archetype: dict[str, dict[str, int]] = {}
    alignment = {"aligned": 0, "conflict": 0}
    iso_overlap = {"iso_vs_neo_high": 0, "iso_vs_kbo_high": 0, "iso_top_and_competing": 0}

    iso_rank_rows: list[dict[str, Any]] = []

    for row in cand_rows:
        cid = row["candidate_id"]
        archetype = row["mock_archetype_label"] or "unknown"
        archetype_counts[archetype] = archetype_counts.get(archetype, 0) + 1

        scores = db.get_latest_scores(cid)
        if not scores:
            continue

        score_map = {s["detector_name"]: float(s["score"]) for s in scores}
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

        iso = score_map.get("iso_detector", 0.0)
        neo = score_map.get("neo_detector", 0.0)
        kbo = score_map.get("kbo_detector", 0.0)
        if iso >= 0.6 and neo >= 0.6:
            iso_overlap["iso_vs_neo_high"] += 1
        if iso >= 0.6 and kbo >= 0.6:
            iso_overlap["iso_vs_kbo_high"] += 1
        if det == "iso_detector" and (neo >= 0.5 or kbo >= 0.5):
            iso_overlap["iso_top_and_competing"] += 1

        iso_rank_rows.append(
            {
                "candidate_id": cid,
                "archetype": archetype,
                "iso_score": iso,
                "neo_score": neo,
                "kbo_score": kbo,
                "top_detector": det,
            }
        )

    iso_rank_rows = sorted(iso_rank_rows, key=lambda r: r["iso_score"], reverse=True)[:top_iso_limit]

    return {
        "archetype_counts": archetype_counts,
        "top_detector_by_archetype": top_detector_by_archetype,
        "alignment": alignment,
        "iso_overlap": iso_overlap,
        "top_iso_candidates": iso_rank_rows,
    }
