from datetime import datetime, timezone
from math import sqrt

from celestial_triage.features.orbit import compute_orbit_scaffold_features, heading_deg


def _safe_div(num: float, den: float) -> float:
    return 0.0 if den == 0 else num / den


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def extract_shared_features(detections: list[dict]) -> dict:
    if not detections:
        return {}

    detections = sorted(detections, key=lambda d: d["timestamp"])

    t0 = _parse_ts(detections[0]["timestamp"])
    t1 = _parse_ts(detections[-1]["timestamp"])
    span_h = max(0.0, (t1 - t0).total_seconds() / 3600.0)

    mags = [float(d["magnitude"]) for d in detections]
    class_conf = [float(d.get("class_confidence", 0.0)) for d in detections]
    mag_delta_abs = abs(mags[-1] - mags[0]) if len(mags) > 1 else 0.0
    brightness_trend = mags[-1] - mags[0] if len(mags) > 1 else 0.0

    moving_vals = [int(d["moving_flag"]) for d in detections]
    poor_catalog_vals = [1 if d["catalog_match_status"] in ("poor_match", "no_match") else 0 for d in detections]

    ra0, dec0 = float(detections[0]["ra"]), float(detections[0]["dec"])
    ra1, dec1 = float(detections[-1]["ra"]), float(detections[-1]["dec"])
    angular_motion = sqrt((ra1 - ra0) ** 2 + (dec1 - dec0) ** 2)
    motion_rate = angular_motion / span_h if span_h > 0 else 0.0

    step_lengths: list[float] = []
    headings: list[float] = []
    heading_changes: list[float] = []
    prev_heading = None
    for i in range(1, len(detections)):
        d_prev = detections[i - 1]
        d_cur = detections[i]
        step = sqrt((float(d_cur["ra"]) - float(d_prev["ra"])) ** 2 + (float(d_cur["dec"]) - float(d_prev["dec"])) ** 2)
        step_lengths.append(step)
        h = heading_deg(
            float(d_prev["ra"]),
            float(d_prev["dec"]),
            float(d_cur["ra"]),
            float(d_cur["dec"]),
        )
        headings.append(h)
        if prev_heading is not None:
            hd = abs(h - prev_heading)
            heading_changes.append(min(hd, 360.0 - hd))
        prev_heading = h

    if step_lengths:
        mean_step = sum(step_lengths) / len(step_lengths)
        variance = sum((x - mean_step) ** 2 for x in step_lengths) / len(step_lengths)
        stdev = variance**0.5
        motion_consistency = max(0.0, 1.0 - _safe_div(stdev, mean_step + 1e-6))
        path_smoothness = _clamp(1.0 - min(1.0, _safe_div(stdev, max(0.25, mean_step))))
    else:
        motion_consistency = 0.0
        path_smoothness = 0.0

    if headings:
        mean_h = sum(headings) / len(headings)
        heading_var = sum((h - mean_h) ** 2 for h in headings) / len(headings)
        heading_std = heading_var**0.5
        direction_consistency = max(0.0, 1.0 - min(1.0, heading_std / 180.0))
        heading_placeholder = mean_h
    else:
        direction_consistency = 0.0
        heading_placeholder = 0.0

    if heading_changes:
        mean_hc = sum(heading_changes) / len(heading_changes)
        heading_change_consistency = _clamp(1.0 - min(1.0, mean_hc / 90.0))
    else:
        heading_change_consistency = direction_consistency

    trajectory_quality = _clamp(
        0.40 * motion_consistency + 0.35 * direction_consistency + 0.25 * path_smoothness
    )

    orbit_fit_placeholder = max(0.0, 1.0 - min(1.0, angular_motion / 50.0))
    hyperbolic_placeholder = min(1.0, (angular_motion / 20.0) * _safe_div(sum(poor_catalog_vals), len(detections)))
    anomaly_index = min(1.0, (mag_delta_abs / 2.5) * (1.0 - _safe_div(sum(class_conf), len(detections))))

    orbit = compute_orbit_scaffold_features(
        motion_rate_deg_per_hour=motion_rate,
        motion_consistency=motion_consistency,
        poor_catalog_fraction=_safe_div(sum(poor_catalog_vals), len(detections)),
        detection_count=len(detections),
        detection_span_hours=span_h,
        direction_consistency=direction_consistency,
    )

    return {
        "detection_count": len(detections),
        "first_seen": detections[0]["timestamp"],
        "last_seen": detections[-1]["timestamp"],
        "detection_span_hours": span_h,
        "avg_magnitude": sum(mags) / len(mags),
        "mag_delta_abs": mag_delta_abs,
        "brightness_trend": brightness_trend,
        "moving_fraction": _safe_div(sum(moving_vals), len(moving_vals)),
        "motion_rate_deg_per_hour": motion_rate,
        "motion_consistency_placeholder": motion_consistency,
        "direction_consistency_placeholder": direction_consistency,
        "heading_deg_placeholder": heading_placeholder,
        "heading_change_consistency": heading_change_consistency,
        "path_smoothness_placeholder": path_smoothness,
        "trajectory_quality": trajectory_quality,
        "poor_catalog_fraction": _safe_div(sum(poor_catalog_vals), len(poor_catalog_vals)),
        "avg_class_confidence": _safe_div(sum(class_conf), len(class_conf)),
        "angular_motion_placeholder": angular_motion,
        "orbit_fit_quality": orbit["orbit_fit_quality"],
        "eccentricity_placeholder": orbit["eccentricity_placeholder"],
        "hyperbolic_likelihood": orbit["hyperbolic_likelihood"],
        "inbound_outbound_placeholder": orbit["inbound_outbound_placeholder"],
        "orbit_fit_placeholder": orbit_fit_placeholder,
        "hyperbolic_likelihood_placeholder": hyperbolic_placeholder,
        "anomaly_index_placeholder": anomaly_index,
    }
