from datetime import datetime
from math import sqrt


def _safe_div(num: float, den: float) -> float:
    return 0.0 if den == 0 else num / den


def extract_shared_features(detections: list[dict]) -> dict:
    if not detections:
        return {}

    detections = sorted(detections, key=lambda d: d["timestamp"])

    t0 = datetime.fromisoformat(detections[0]["timestamp"])
    t1 = datetime.fromisoformat(detections[-1]["timestamp"])
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

    # Motion consistency placeholder: step-length stability over ordered detections.
    step_lengths: list[float] = []
    for i in range(1, len(detections)):
        d_prev = detections[i - 1]
        d_cur = detections[i]
        step = sqrt((float(d_cur["ra"]) - float(d_prev["ra"])) ** 2 + (float(d_cur["dec"]) - float(d_prev["dec"])) ** 2)
        step_lengths.append(step)

    if step_lengths:
        mean_step = sum(step_lengths) / len(step_lengths)
        variance = sum((x - mean_step) ** 2 for x in step_lengths) / len(step_lengths)
        stdev = variance**0.5
        motion_consistency = max(0.0, 1.0 - _safe_div(stdev, mean_step + 1e-6))
    else:
        motion_consistency = 0.0

    orbit_fit_placeholder = max(0.0, 1.0 - min(1.0, angular_motion / 50.0))
    hyperbolic_placeholder = min(1.0, (angular_motion / 20.0) * _safe_div(sum(poor_catalog_vals), len(detections)))
    anomaly_index = min(1.0, (mag_delta_abs / 2.5) * (1.0 - _safe_div(sum(class_conf), len(detections))))

    return {
        "detection_count": len(detections),
        "first_seen": detections[0]["timestamp"],
        "last_seen": detections[-1]["timestamp"],
        "detection_span_hours": span_h,
        "avg_magnitude": sum(mags) / len(mags),
        "mag_delta_abs": mag_delta_abs,
        "brightness_trend": brightness_trend,
        "moving_fraction": _safe_div(sum(moving_vals), len(moving_vals)),
        "motion_consistency_placeholder": motion_consistency,
        "poor_catalog_fraction": _safe_div(sum(poor_catalog_vals), len(poor_catalog_vals)),
        "avg_class_confidence": _safe_div(sum(class_conf), len(class_conf)),
        "angular_motion_placeholder": angular_motion,
        "orbit_fit_placeholder": orbit_fit_placeholder,
        "hyperbolic_likelihood_placeholder": hyperbolic_placeholder,
        "anomaly_index_placeholder": anomaly_index,
    }
