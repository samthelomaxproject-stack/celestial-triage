import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from celestial_triage.models.entities import NormalizedDetection, RawEvent


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "t"}:
            return True
        if v in {"0", "false", "no", "n", "f"}:
            return False
    return default


def normalize_event_safe(raw: RawEvent) -> Tuple[Optional[NormalizedDetection], list[str]]:
    """Normalize a raw event with schema-hardening and graceful fallbacks.

    Returns (NormalizedDetection | None, warnings).
    Returns None if record is unusable (e.g., missing/invalid RA+Dec).
    """
    p = raw.payload
    warnings: list[str] = []

    ra = _as_float(p.get("ra", p.get("ra_deg", p.get("ramean"))), default=float("nan"))
    dec = _as_float(p.get("dec", p.get("decl", p.get("dec_deg", p.get("decmean")))), default=float("nan"))
    if ra != ra or dec != dec:  # NaN check
        warnings.append("missing_or_invalid_coordinates")
        return None, warnings

    magnitude = _as_float(p.get("mag", p.get("magnitude", p.get("magpsf"))), default=99.0)
    mag_change = _as_float(
        p.get("mag_change", p.get("magnitude_change", p.get("dmag"))),
        default=0.0,
    )
    moving = _as_bool(p.get("moving", p.get("moving_flag", p.get("is_moving"))), default=False)

    class_label = str(p.get("class_label", p.get("label", "unknown")))
    class_conf = _as_float(p.get("class_confidence", p.get("score", p.get("confidence"))), default=0.0)
    catalog_match = str(
        p.get("catalog_match", p.get("catalog_match_status", p.get("match_status", "no_match")))
    )

    if magnitude >= 90:
        warnings.append("magnitude_fallback_used")

    det = NormalizedDetection(
        detection_id=str(uuid.uuid4()),
        source_id=raw.source_id,
        broker_name=raw.broker_name,
        timestamp=raw.timestamp,
        ra=ra,
        dec=dec,
        magnitude=magnitude,
        magnitude_change=mag_change,
        moving_flag=moving,
        class_label=class_label,
        class_confidence=class_conf,
        catalog_match_status=catalog_match,
        raw_payload_reference=raw.raw_event_id,
        ingest_time=datetime.now(timezone.utc),
        mock_archetype_label=str(p.get("mock_archetype_label", "")),
    )
    return det, warnings


def normalize_event(raw: RawEvent) -> NormalizedDetection:
    det, warnings = normalize_event_safe(raw)
    if det is None:
        raise ValueError(f"Unable to normalize record {raw.raw_event_id}: {','.join(warnings)}")
    return det
