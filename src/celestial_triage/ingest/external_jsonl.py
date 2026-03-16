import json
from datetime import datetime, timezone
from pathlib import Path

from celestial_triage.ingest.base import BrokerAdapter
from celestial_triage.models.entities import RawEvent


class JsonlExternalAdapter(BrokerAdapter):
    """Minimal external-source adapter scaffold.

    Reads newline-delimited JSON objects from a local file and maps them to RawEvent.
    This is intentionally narrow and isolated for first real-source readiness.
    """

    def __init__(self, path: Path, broker_name: str = "external_jsonl") -> None:
        self.path = path
        self.broker_name = broker_name

    def fetch_events(self) -> list[RawEvent]:
        events: list[RawEvent] = []
        if not self.path.exists():
            return events

        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                source_id = str(row.get("source_id") or row.get("objectId") or "UNKNOWN")
                ts_raw = row.get("timestamp")
                ts = datetime.fromisoformat(ts_raw) if ts_raw else datetime.now(timezone.utc)
                raw_id = str(row.get("raw_event_id") or row.get("candid") or f"{source_id}-{ts.isoformat()}")
                events.append(
                    RawEvent(
                        raw_event_id=raw_id,
                        broker_name=self.broker_name,
                        source_id=source_id,
                        timestamp=ts,
                        payload=row,
                    )
                )
        return events
