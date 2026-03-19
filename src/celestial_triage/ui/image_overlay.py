from __future__ import annotations

from datetime import datetime
from math import cos, radians, sqrt
from typing import Any


def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def _to_dt(v: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def format_radec_overlay(ra: Any, dec: Any) -> str | None:
    fra = _to_float(ra)
    fdec = _to_float(dec)
    if fra is None or fdec is None:
        return None
    return f"RA {fra:.6f}  DEC {fdec:.6f}"


def build_track_offsets(
    detections: list[dict[str, Any]],
    center_ra: Any,
    center_dec: Any,
    max_radius_px: float = 20.0,
    base_px_per_arcsec: float = 2.0,
) -> list[tuple[float, float]]:
    """Return per-detection track offsets (pixels) relative to candidate center.

    Output coordinates are (dx_px, dy_px) where +x is right, +y is down.
    Requires at least 2 valid detections; otherwise returns [].
    """
    cra = _to_float(center_ra)
    cdec = _to_float(center_dec)
    if cra is None or cdec is None:
        return []

    rows: list[tuple[datetime, float, float]] = []
    for d in detections:
        ra = _to_float(d.get("ra"))
        dec = _to_float(d.get("dec"))
        if ra is None or dec is None:
            continue
        rows.append((_to_dt(d.get("timestamp")), ra, dec))

    if len(rows) < 2:
        return []

    rows.sort(key=lambda x: x[0])

    cosd = max(0.1, cos(radians(cdec)))
    arcsec_offsets: list[tuple[float, float]] = []
    max_dist = 0.0
    for _ts, ra, dec in rows:
        dra_arcsec = (ra - cra) * 3600.0 * cosd
        ddec_arcsec = (dec - cdec) * 3600.0
        arcsec_offsets.append((dra_arcsec, ddec_arcsec))
        max_dist = max(max_dist, sqrt(dra_arcsec**2 + ddec_arcsec**2))

    if max_dist <= 0:
        return []

    scale = min(base_px_per_arcsec, max_radius_px / max_dist)

    out: list[tuple[float, float]] = []
    for dx_arcsec, dy_arcsec in arcsec_offsets:
        out.append((dx_arcsec * scale, -dy_arcsec * scale))
    return out
