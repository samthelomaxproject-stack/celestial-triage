from __future__ import annotations

from math import cos, radians, sqrt
from typing import Any

from celestial_triage.scoring.followup import build_followup_priority
from celestial_triage.scoring.interpretation import build_interpretation_summary
from celestial_triage.storage.db import Database


def _ang_sep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    dra = (ra2 - ra1) * cos(radians((dec1 + dec2) / 2.0))
    ddec = dec2 - dec1
    return sqrt(dra * dra + ddec * ddec)


def _as_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def build_candidate_context(db: Database, candidate_id: str) -> dict[str, Any]:
    try:
        cand = db.get_candidate_with_features(candidate_id)
    except Exception:
        cand = None

    if not cand:
        return {
            "candidate_id": candidate_id,
            "ra": None,
            "dec": None,
            "context_status": "limited",
            "host_context_note": "No context available",
            "crowdedness_note": "unknown",
            "catalog_context_note": "unknown",
            "provenance_note": "",
            "concise_explanation": "Insufficient context data.",
            "plate_solve_count": 0,
            "latest_plate_solve_timestamp": None,
            "latest_plate_solve_backend": None,
            "latest_plate_solve_status": None,
            # legacy keys used by existing export/UI paths
            "nearest_object_summary": "No context available",
            "host_hint": "unknown",
            "nearest_object_arcsec": None,
            "field_density": "unknown",
            "catalog_match_status": "unknown",
            "provenance_summary": "",
            "context_interpretation": "Insufficient context data.",
        }

    ra = _as_float(cand.get("average_ra"))
    dec = _as_float(cand.get("average_dec"))
    if ra is None or dec is None:
        return {
            "candidate_id": candidate_id,
            "ra": ra,
            "dec": dec,
            "context_status": "limited",
            "host_context_note": "Position unavailable",
            "crowdedness_note": "unknown",
            "catalog_context_note": "unknown",
            "provenance_note": "",
            "concise_explanation": "Candidate coordinates unavailable; context is limited.",
            "plate_solve_count": 0,
            "latest_plate_solve_timestamp": None,
            "latest_plate_solve_backend": None,
            "latest_plate_solve_status": None,
            "nearest_object_summary": "No context available",
            "host_hint": "unknown",
            "nearest_object_arcsec": None,
            "field_density": "unknown",
            "catalog_match_status": "unknown",
            "provenance_summary": "",
            "context_interpretation": "Candidate coordinates unavailable; context is limited.",
        }

    nearest: tuple[str, str, float] | None = None
    neighbors_02 = 0
    neighbors_05 = 0

    with db.conn() as c:
        rows = c.execute(
            "SELECT candidate_id, source_id, average_ra, average_dec FROM candidates WHERE candidate_id != ?",
            (candidate_id,),
        ).fetchall()
        prov_rows = c.execute(
            """
            SELECT d.broker_name, COUNT(*) as n
            FROM detections d
            JOIN candidate_detections cd ON cd.detection_id=d.detection_id
            WHERE cd.candidate_id=?
            GROUP BY d.broker_name
            """,
            (candidate_id,),
        ).fetchall()
        plate_rows = c.execute(
            """
            SELECT solve_id, solved_at, backend, status
            FROM plate_solves
            WHERE candidate_id=?
            ORDER BY solved_at DESC
            """,
            (candidate_id,),
        ).fetchall()

    for r in rows:
        rra = _as_float(r["average_ra"])
        rdec = _as_float(r["average_dec"])
        if rra is None or rdec is None:
            continue
        dist = _ang_sep_deg(ra, dec, rra, rdec)
        if dist <= 0.2:
            neighbors_02 += 1
        if dist <= 0.5:
            neighbors_05 += 1
        if nearest is None or dist < nearest[2]:
            nearest = (str(r["candidate_id"]), str(r["source_id"]), dist)

    latest = db.get_latest_detection_for_candidate(candidate_id) or {}
    catalog_match = str(latest.get("catalog_match_status") or "unknown")

    if catalog_match in ("matched", "likely_match"):
        host_hint = "likely-host-associated"
    elif catalog_match in ("poor_match", "no_match"):
        host_hint = "no-obvious-host"
    else:
        host_hint = "unknown"

    if neighbors_02 >= 5:
        density = "crowded"
    elif neighbors_05 <= 1:
        density = "isolated"
    else:
        density = "moderate"

    nearest_arcsec = round((nearest[2] * 3600.0), 2) if nearest else None
    nearest_summary = (
        f"Nearest tracked object source={nearest[1]} at {nearest_arcsec:.2f} arcsec"
        if nearest and nearest_arcsec is not None
        else "No nearby tracked object in current local candidate set"
    )

    provenance = {str(r["broker_name"]): int(r["n"]) for r in prov_rows}
    provenance_summary = ", ".join([f"{k}:{v}" for k, v in provenance.items()])

    plate_solve_count = len(plate_rows)
    latest_plate = plate_rows[0] if plate_rows else None
    latest_plate_solve_timestamp = str(latest_plate["solved_at"]) if latest_plate else None
    latest_plate_solve_backend = str(latest_plate["backend"]) if latest_plate else None
    latest_plate_solve_status = str(latest_plate["status"]) if latest_plate else None
    plate_solve_note = (
        f"plate_solve:{plate_solve_count}"
        f" ({latest_plate_solve_status or 'unknown'} via {latest_plate_solve_backend or 'unknown'})"
        if plate_solve_count > 0
        else ""
    )

    scores = db.get_latest_scores(candidate_id)
    score_map = {s["detector_name"]: float(s["score"]) for s in scores}
    features = cand.get("features", {})
    review_state = str(cand.get("review_status") or "new")
    interp = build_interpretation_summary(features, score_map)
    follow = build_followup_priority(features, score_map, review_state)
    primary_interp = str(interp.get("primary_interpretation") or "unknown")
    follow_pri = str(follow.get("priority") or "low")

    images = db.get_images_for_candidate(candidate_id)
    image_kinds = sorted({str(i.get("kind") or "") for i in images if i.get("kind")})
    image_note = "none" if not image_kinds else ", ".join(image_kinds)

    context_status = "rich" if (nearest is not None or images or provenance) else "limited"

    # Build concise, analyst-friendly explanation
    density_desc = {"isolated": "Isolated field", "moderate": "Moderately crowded", "crowded": "Crowded field"}
    field_text = density_desc.get(density, f"{density.capitalize()} field")
    
    catalog_desc = {
        "matched": "strong catalog match",
        "likely_match": "likely catalog match",
        "poor_match": "weak catalog match",
        "no_match": "no catalog match"
    }
    catalog_text = catalog_desc.get(catalog_match, f"catalog {catalog_match}")
    
    host_desc = {
        "likely-host-associated": "likely host-associated",
        "no-obvious-host": "no obvious host",
        "unknown": "host unknown"
    }
    host_text = host_desc.get(host_hint, host_hint)
    
    # Compose natural-language summary
    parts = [f"{field_text}.", f"{catalog_text.capitalize()}, {host_text}."]
    
    if follow_pri in ("high", "critical"):
        parts.append(f"{follow_pri.upper()} priority follow-up.")
    
    if primary_interp not in ("unknown", "unclear"):
        parts.append(f"Interpreted as {primary_interp}.")
    
    concise = " ".join(parts)

    return {
        "candidate_id": candidate_id,
        "ra": ra,
        "dec": dec,
        "context_status": context_status,
        "host_context_note": host_hint,
        "crowdedness_note": density,
        "catalog_context_note": catalog_match,
        "provenance_note": " | ".join([p for p in [provenance_summary, plate_solve_note] if p]) or "unknown",
        "candidate_history_count": len(db.get_detections_for_candidate(candidate_id)),
        "followup_priority": follow_pri,
        "interpretation_summary": primary_interp,
        "image_availability": image_note,
        "nearest_object_summary": nearest_summary,
        "nearest_object_arcsec": nearest_arcsec,
        "concise_explanation": concise,
        "plate_solve_count": plate_solve_count,
        "latest_plate_solve_timestamp": latest_plate_solve_timestamp,
        "latest_plate_solve_backend": latest_plate_solve_backend,
        "latest_plate_solve_status": latest_plate_solve_status,
        # legacy-compatible keys
        "host_hint": host_hint,
        "field_density": density,
        "catalog_match_status": catalog_match,
        "provenance_summary": provenance_summary,
        "context_interpretation": (
            f"Field appears {density}; catalog status is {catalog_match}; "
            f"host hint: {host_hint}. {nearest_summary}."
        ),
    }
