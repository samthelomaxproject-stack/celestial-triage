from math import atan2, degrees


def compute_orbit_scaffold_features(
    motion_rate_deg_per_hour: float,
    motion_consistency: float,
    poor_catalog_fraction: float,
    detection_count: int,
) -> dict:
    """Simple explainable orbit-feature scaffolding for v1.

    This is intentionally placeholder logic (not full orbital determination).
    """
    orbit_fit_quality = max(0.0, min(1.0, 0.6 * motion_consistency + 0.4 * min(1.0, detection_count / 6.0)))
    eccentricity_placeholder = max(0.0, min(1.5, 0.2 + motion_rate_deg_per_hour * 0.15))
    hyperbolic_likelihood = max(
        0.0,
        min(1.0, 0.5 * max(0.0, eccentricity_placeholder - 1.0) + 0.5 * poor_catalog_fraction),
    )
    inbound_outbound_placeholder = "unknown"
    if detection_count >= 3:
        inbound_outbound_placeholder = "inbound_or_outbound_candidate"

    return {
        "orbit_fit_quality": orbit_fit_quality,
        "eccentricity_placeholder": eccentricity_placeholder,
        "hyperbolic_likelihood": hyperbolic_likelihood,
        "inbound_outbound_placeholder": inbound_outbound_placeholder,
    }


def heading_deg(ra_from: float, dec_from: float, ra_to: float, dec_to: float) -> float:
    d_ra = ra_to - ra_from
    d_dec = dec_to - dec_from
    return (degrees(atan2(d_ra, d_dec)) + 360.0) % 360.0
