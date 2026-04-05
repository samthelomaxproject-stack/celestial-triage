from __future__ import annotations

from datetime import datetime, timezone
from math import acos, atan2, cos, degrees, radians, sin, sqrt
from statistics import mean, pstdev
from typing import Any


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _as_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def _parse_ts(v: Any) -> datetime | None:
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def angular_separation_arcsec(ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float) -> float:
    """Great-circle angular separation in arcseconds."""
    ra1 = radians(ra1_deg)
    dec1 = radians(dec1_deg)
    ra2 = radians(ra2_deg)
    dec2 = radians(dec2_deg)
    c = sin(dec1) * sin(dec2) + cos(dec1) * cos(dec2) * cos(ra1 - ra2)
    c = _clamp(c, -1.0, 1.0)
    return degrees(acos(c)) * 3600.0


def position_angle_deg(ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float) -> float:
    """Position angle from point 1 to 2, degrees in [0,360)."""
    ra1 = radians(ra1_deg)
    dec1 = radians(dec1_deg)
    ra2 = radians(ra2_deg)
    dec2 = radians(dec2_deg)
    dra = ra2 - ra1
    y = sin(dra) * cos(dec2)
    x = cos(dec1) * sin(dec2) - sin(dec1) * cos(dec2) * cos(dra)
    return (degrees(atan2(y, x)) + 360.0) % 360.0


def _angular_diff_deg(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def analyze_candidate_motion(detections: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute cautious multi-epoch motion metrics and anomaly heuristics.

    Uses only detection history currently stored in the local database.
    """
    prepared: list[tuple[datetime, float, float]] = []
    for d in detections:
        ts = _parse_ts(d.get("timestamp"))
        ra = _as_float(d.get("ra"))
        dec = _as_float(d.get("dec"))
        if ts is None or ra is None or dec is None:
            continue
        prepared.append((ts, ra, dec))

    prepared.sort(key=lambda t: t[0])
    n = len(prepared)

    base = {
        "detection_count_used": n,
        "total_time_span_sec": 0.0,
        "angular_displacement_arcsec": 0.0,
        "average_angular_velocity_arcsec_per_sec": 0.0,
        "average_position_angle_deg": None,
        "segment_velocities_arcsec_per_sec": [],
        "direction_consistency": None,
        "acceleration_proxy_arcsec_per_sec2": None,
        "curvature_proxy_deg": None,
        "motion_consistency_score": None,
        "motion_anomaly_flag": False,
        "motion_anomaly_score": 0.0,
        "motion_anomaly_reason": "insufficient data",
        "motion_state": "insufficient data",
    }

    if n < 2:
        return base

    t0, ra0, dec0 = prepared[0]
    t1, ra1, dec1 = prepared[-1]
    span = max(0.0, (t1 - t0).total_seconds())
    disp = angular_separation_arcsec(ra0, dec0, ra1, dec1)
    avg_vel = (disp / span) if span > 0 else 0.0
    avg_pa = position_angle_deg(ra0, dec0, ra1, dec1)

    seg_vel: list[float] = []
    seg_pa: list[float] = []
    for (ta, raa, deca), (tb, rab, decb) in zip(prepared, prepared[1:]):
        dt = (tb - ta).total_seconds()
        if dt <= 0:
            continue
        sdisp = angular_separation_arcsec(raa, deca, rab, decb)
        seg_vel.append(sdisp / dt)
        seg_pa.append(position_angle_deg(raa, deca, rab, decb))

    direction_consistency = None
    accel_proxy = None
    curvature_proxy = None
    motion_consistency_score = None

    if len(seg_pa) >= 2:
        # 1.0 = highly consistent, 0.0 = highly inconsistent.
        d_changes = [_angular_diff_deg(seg_pa[i], seg_pa[i - 1]) for i in range(1, len(seg_pa))]
        mean_dir_change = mean(d_changes)
        direction_consistency = _clamp(1.0 - (mean_dir_change / 90.0), 0.0, 1.0)
        curvature_proxy = mean_dir_change

    if len(seg_vel) >= 2:
        # average absolute segment acceleration between adjacent segments.
        accel_vals: list[float] = []
        for i in range(1, len(seg_vel)):
            dt = (prepared[i + 1][0] - prepared[i - 1][0]).total_seconds() / 2.0
            if dt <= 0:
                continue
            accel_vals.append(abs(seg_vel[i] - seg_vel[i - 1]) / dt)
        if accel_vals:
            accel_proxy = mean(accel_vals)

    if len(seg_vel) >= 2:
        vel_std = pstdev(seg_vel)
        vel_mean = max(mean(seg_vel), 1e-9)
        vel_cv = vel_std / vel_mean
    else:
        vel_cv = 0.0

    if direction_consistency is not None:
        motion_consistency_score = _clamp(0.65 * direction_consistency + 0.35 * (1.0 - _clamp(vel_cv, 0.0, 1.0)), 0.0, 1.0)

    # Conservative first-pass anomaly heuristic
    score = 0.0
    reasons: list[str] = []

    if span > 0 and disp >= 60.0 and span <= 2 * 3600:
        score += 0.45
        reasons.append("large displacement in short span")

    if direction_consistency is not None and direction_consistency < 0.45:
        score += 0.30
        reasons.append("inconsistent direction changes")

    if len(seg_vel) >= 2:
        vmin = max(min(seg_vel), 1e-9)
        vmax = max(seg_vel)
        ratio = vmax / vmin
        if ratio >= 3.0 and vmax >= 0.02:
            score += 0.30
            reasons.append("segment velocity changed sharply")

    if n < 3:
        # Avoid overclaiming on sparse history.
        score *= 0.7

    score = _clamp(score, 0.0, 1.0)
    flag = score >= 0.70 and n >= 2

    if n < 2:
        state = "insufficient data"
    elif flag:
        state = "unusual"
    else:
        state = "stable"

    base.update(
        {
            "detection_count_used": n,
            "total_time_span_sec": span,
            "angular_displacement_arcsec": disp,
            "average_angular_velocity_arcsec_per_sec": avg_vel,
            "average_position_angle_deg": avg_pa,
            "segment_velocities_arcsec_per_sec": seg_vel,
            "direction_consistency": direction_consistency,
            "acceleration_proxy_arcsec_per_sec2": accel_proxy,
            "curvature_proxy_deg": curvature_proxy,
            "motion_consistency_score": motion_consistency_score,
            "motion_anomaly_flag": flag,
            "motion_anomaly_score": score,
            "motion_anomaly_reason": "; ".join(reasons) if reasons else "no strong local anomaly signal",
            "motion_state": state,
        }
    )
    return base
