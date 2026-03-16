from celestial_triage.scoring.common import clamp01


def evaluate(features: dict) -> tuple[float, list[str]]:
    # Strongly ISO-focused weighting (transparent heuristics)
    motion_rate = clamp01(features.get("motion_rate_deg_per_hour", 0.0) / 2.0)
    direction_consistency = clamp01(features.get("direction_consistency_placeholder", 0.0))
    orbit_fit_quality = clamp01(features.get("orbit_fit_quality", 0.0))
    eccentricity = clamp01((features.get("eccentricity_placeholder", 0.0) - 0.8) / 0.7)
    hyperbolic = clamp01(features.get("hyperbolic_likelihood", features.get("hyperbolic_likelihood_placeholder", 0.0)))
    poor_catalog = clamp01(features.get("poor_catalog_fraction", 0.0))
    detection_count = clamp01(features.get("detection_count", 0) / 6.0)
    span = clamp01(features.get("detection_span_hours", 0.0) / 72.0)
    inbound_outbound = str(features.get("inbound_outbound_placeholder", "unknown"))
    io_bonus = 0.08 if inbound_outbound != "unknown" else 0.0

    # Emphasize hyperbolic + eccentric + catalog mismatch + sustained track evidence.
    score = (
        0.30 * hyperbolic
        + 0.20 * eccentricity
        + 0.12 * poor_catalog
        + 0.10 * motion_rate
        + 0.10 * direction_consistency
        + 0.08 * orbit_fit_quality
        + 0.05 * detection_count
        + 0.05 * span
        + io_bonus
    )

    score = clamp01(score)

    reasons = [
        f"hyperbolic_likelihood={hyperbolic:.2f}",
        f"eccentricity_placeholder={eccentricity:.2f}",
        f"poor_catalog_fraction={poor_catalog:.2f}",
        f"motion_rate_deg_per_hour={motion_rate:.2f}",
        f"direction_consistency={direction_consistency:.2f}",
        f"orbit_fit_quality={orbit_fit_quality:.2f}",
        f"detection_count_norm={detection_count:.2f}",
        f"detection_span_norm={span:.2f}",
        f"inbound_outbound={inbound_outbound}",
    ]
    return score, reasons
