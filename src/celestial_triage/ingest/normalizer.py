import uuid
from datetime import datetime, timezone

from celestial_triage.models.entities import NormalizedDetection, RawEvent


def normalize_event(raw: RawEvent) -> NormalizedDetection:
    p = raw.payload
    return NormalizedDetection(
        detection_id=str(uuid.uuid4()),
        source_id=raw.source_id,
        broker_name=raw.broker_name,
        timestamp=raw.timestamp,
        ra=float(p.get("ra", 0.0)),
        dec=float(p.get("dec", 0.0)),
        magnitude=float(p.get("mag", 99.0)),
        magnitude_change=float(p.get("mag_change", 0.0)),
        moving_flag=bool(p.get("moving", False)),
        class_label=str(p.get("class_label", "unknown")),
        class_confidence=float(p.get("class_confidence", 0.0)),
        catalog_match_status=str(p.get("catalog_match", "no_match")),
        raw_payload_reference=raw.raw_event_id,
        ingest_time=datetime.now(timezone.utc),
        mock_archetype_label=str(p.get("mock_archetype_label", "")),
    )
