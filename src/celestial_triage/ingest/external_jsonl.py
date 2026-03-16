import json
from datetime import datetime, timezone
from pathlib import Path

from celestial_triage.ingest.base import BrokerAdapter
from celestial_triage.models.entities import RawEvent
from celestial_triage.utils.logging import get_logger

LOGGER = get_logger("external_jsonl")


class JsonlExternalAdapter(BrokerAdapter):
    """Minimal external-source adapter scaffold.

    Reads newline-delimited JSON objects from a local file and maps them to RawEvent.
    Handles malformed lines gracefully (skip + log warning).
    """

    def __init__(self, path: Path, broker_name: str = "external_jsonl") -> None:
        self.path = path
        self.broker_name = broker_name

    def fetch_events(self) -> list[RawEvent]:
        events: list[RawEvent] = []
        if not self.path.exists():
            LOGGER.warning("Input JSONL not found: %s", self.path)
            return events

        with self.path.open() as f:
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    LOGGER.warning("Skipping malformed JSONL line %d", i)
                    continue

                source_id = str(row.get("source_id") or row.get("objectId") or "")
                if not source_id:
                    LOGGER.warning("Skipping line %d: missing source_id/objectId", i)
                    continue

                ts_raw = row.get("timestamp")
                ts = datetime.now(timezone.utc)
                if ts_raw:
                    try:
                        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    except ValueError:
                        LOGGER.warning("Line %d has invalid timestamp; using now()", i)

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

        LOGGER.info("Loaded %d external raw events from %s", len(events), self.path)
        return events
