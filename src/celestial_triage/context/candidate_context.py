from __future__ import annotations

from math import cos, radians, sqrt
from typing import Any

from celestial_triage.storage.db import Database


def _ang_sep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    dra = (ra2 - ra1) * cos(radians((dec1 + dec2) / 2.0))
    ddec = dec2 - dec1
    return sqrt(dra * dra + ddec * ddec)


def build_candidate_context(db: Database, candidate_id: str) -> dict[str, Any]:
    try:
        cand = db.get_candidate_with_features(candidate_id)
    except Exception:
        cand = None
    if not cand:
        return {
            "nearest_object_summary": "No context available",
            "host_hint": "unknown",
            "nearest_object_arcsec": None,
            "field_density": "unknown",
            "catalog_match_status": "unknown",
            "provenance_summary": "",
            "context_interpretation": "Insufficient context data.",
        }

    ra = float(cand.get("average_ra") or 0.0)
    dec = float(cand.get("average_dec") or 0.0)

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

    for r in rows:
        dist = _ang_sep_deg(ra, dec, float(r["average_ra"]), float(r["average_dec"]))
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

    interpretation = (
        f"Field appears {density}; catalog status is {catalog_match}; "
        f"host hint: {host_hint}. {nearest_summary}."
    )

    return {
        "nearest_object_summary": nearest_summary,
        "host_hint": host_hint,
        "nearest_object_arcsec": nearest_arcsec,
        "field_density": density,
        "neighbor_count_within_0p2deg": neighbors_02,
        "neighbor_count_within_0p5deg": neighbors_05,
        "catalog_match_status": catalog_match,
        "provenance_summary": provenance_summary,
        "context_interpretation": interpretation,
    }
