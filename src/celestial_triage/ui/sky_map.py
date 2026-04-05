from __future__ import annotations

from math import isfinite
from typing import Any

from celestial_triage.motion.analysis import analyze_candidate_motion
from celestial_triage.scoring.followup import build_followup_priority
from celestial_triage.scoring.interpretation import build_interpretation_summary
from celestial_triage.storage.db import Database


def _safe_float(v: Any) -> float | None:
    try:
        x = float(v)
    except Exception:
        return None
    if not isfinite(x):
        return None
    return x


def prepare_candidate_sky_points(db: Database) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for cid in db.list_candidate_ids():
        cand = db.get_candidate_with_features(cid)
        ra = _safe_float(cand.get("average_ra"))
        dec = _safe_float(cand.get("average_dec"))
        if ra is None or dec is None:
            continue

        scores = db.get_latest_scores(cid)
        score_map = {s["detector_name"]: float(s["score"]) for s in scores}
        feats = cand.get("features", {})
        review_state = str(cand.get("review_status") or "new")

        follow = build_followup_priority(feats, score_map, review_state)
        interp = build_interpretation_summary(feats, score_map)

        motion = analyze_candidate_motion(db.get_detections_for_candidate(cid))

        points.append(
            {
                "candidate_id": cid,
                "source_id": cand.get("source_id"),
                "ra": ra,
                "dec": dec,
                "review_state": review_state,
                "followup_priority": follow.get("priority", "low"),
                "followup_score": float(follow.get("priority_score", 0.0)),
                "primary_interpretation": interp.get("primary_interpretation", "unknown"),
                "motion_anomaly_flag": bool(motion.get("motion_anomaly_flag", False)),
            }
        )
    return points


def nearest_point(points: list[dict[str, Any]], x: float, y: float, max_px_dist: float = 12.0) -> dict[str, Any] | None:
    best = None
    best_d2 = None
    for p in points:
        px = float(p.get("_px", 0.0))
        py = float(p.get("_py", 0.0))
        d2 = (px - x) ** 2 + (py - y) ** 2
        if best_d2 is None or d2 < best_d2:
            best_d2 = d2
            best = p
    if best is None or best_d2 is None:
        return None
    if best_d2 > max_px_dist**2:
        return None
    return best
