from datetime import datetime
from math import sqrt


def extract_shared_features(detections: list[dict]) -> dict:
    if not detections:
        return {}

    t0 = datetime.fromisoformat(detections[0]["timestamp"])
    t1 = datetime.fromisoformat(detections[-1]["timestamp"])
    span_h = max(0.0, (t1 - t0).total_seconds() / 3600.0)

    mags = [float(d["magnitude"]) for d in detections]
    mag_delta_abs = abs(mags[-1] - mags[0]) if len(mags) > 1 else 0.0

    moving_vals = [int(d["moving_flag"]) for d in detections]
    poor_catalog_vals = [1 if d["catalog_match_status"] in ("poor_match", "no_match") else 0 for d in detections]

    ra0, dec0 = detections[0]["ra"], detections[0]["dec"]
    ra1, dec1 = detections[-1]["ra"], detections[-1]["dec"]
    angular_motion = sqrt((ra1 - ra0) ** 2 + (dec1 - dec0) ** 2)

    orbit_fit_placeholder = max(0.0, 1.0 - min(1.0, angular_motion / 50.0))
    hyperbolic_placeholder = min(1.0, (angular_motion / 20.0) * (sum(poor_catalog_vals) / len(detections)))
    anomaly_index = min(1.0, (mag_delta_abs / 2.5) * (1.0 - (sum([d["class_confidence"] for d in detections]) / len(detections))))

    return {
        "detection_count": len(detections),
        "detection_span_hours": span_h,
        "avg_magnitude": sum(mags) / len(mags),
        "mag_delta_abs": mag_delta_abs,
        "moving_fraction": sum(moving_vals) / len(moving_vals),
        "poor_catalog_fraction": sum(poor_catalog_vals) / len(poor_catalog_vals),
        "angular_motion_placeholder": angular_motion,
        "orbit_fit_placeholder": orbit_fit_placeholder,
        "hyperbolic_likelihood_placeholder": hyperbolic_placeholder,
        "anomaly_index_placeholder": anomaly_index,
    }
