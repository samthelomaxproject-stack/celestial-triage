from math import atan2, degrees


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def compute_orbit_scaffold_features(
    motion_rate_deg_per_hour: float,
    motion_consistency: float,
    poor_catalog_fraction: float,
    detection_count: int,
    detection_span_hours: float,
    direction_consistency: float,
) -> dict:
    """Heuristic orbit-feature scaffolding for v1 (not physical orbit determination).

    Inputs are candidate-level aggregates derived from detections. Outputs are
    explainable placeholders intended for ranking/triage only.
    """
    motion_rate = max(0.0, motion_rate_deg_per_hour)
    consistency = _clamp(motion_consistency)
    dir_consistency = _clamp(direction_consistency)
    poor_catalog = _clamp(poor_catalog_fraction)

    detect_strength = _clamp(detection_count / 8.0)
    span_strength = _clamp(detection_span_hours / 96.0)

    # Orbit-fit quality: improved with consistent direction/motion and more evidence.
    orbit_fit_quality = _clamp(
        0.30 * consistency
        + 0.20 * dir_consistency
        + 0.25 * detect_strength
        + 0.25 * span_strength
    )

    # Eccentricity placeholder: increases with motion rate and poor catalog support,
    # moderated by available evidence so single-point noise doesn't dominate.
    raw_e = 0.65 + 0.35 * _clamp(motion_rate / 1.5) + 0.25 * poor_catalog + 0.15 * _clamp((detect_strength + span_strength) / 2.0)
    eccentricity_placeholder = max(0.0, min(1.8, raw_e))

    # Hyperbolic-likelihood placeholder: requires e>1 tendency plus poor-catalog and
    # directional evidence. Explicitly heuristic.
    e_excess = _clamp((eccentricity_placeholder - 1.0) / 0.8)
    hyperbolic_likelihood = _clamp(
        0.45 * e_excess
        + 0.20 * poor_catalog
        + 0.15 * dir_consistency
        + 0.10 * consistency
        + 0.10 * _clamp((detect_strength + span_strength) / 2.0)
    )

    # Inbound/outbound placeholder: sign-like proxy from brightness trend is not used
    # here; with available aggregates we only expose confidence class.
    if hyperbolic_likelihood >= 0.7 and orbit_fit_quality >= 0.5:
        inbound_outbound_placeholder = "strong_candidate"
    elif hyperbolic_likelihood >= 0.45:
        inbound_outbound_placeholder = "possible_candidate"
    else:
        inbound_outbound_placeholder = "unknown"

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
