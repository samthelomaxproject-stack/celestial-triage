import random
import uuid
from datetime import datetime, timedelta, timezone

from celestial_triage.ingest.base import BrokerAdapter
from celestial_triage.models.entities import RawEvent


class MockFeedAdapter(BrokerAdapter):
    def __init__(self, count: int = 100, broker_name: str = "mock_broker") -> None:
        self.count = count
        self.broker_name = broker_name

    def fetch_events(self) -> list[RawEvent]:
        now = datetime.now(timezone.utc)
        events: list[RawEvent] = []
        source_pool = [f"SRC-{i:04d}" for i in range(max(10, self.count // 4))]

        for _ in range(self.count):
            source_id = random.choice(source_pool)
            ts = now - timedelta(minutes=random.randint(0, 60 * 24 * 7))
            payload = {
                "ra": random.uniform(0, 360),
                "dec": random.uniform(-90, 90),
                "mag": random.uniform(14, 24),
                "mag_change": random.uniform(-2.5, 2.5),
                "moving": random.random() > 0.55,
                "class_label": random.choice(["unknown", "asteroid", "variable", "artifact"]),
                "class_confidence": random.random(),
                "catalog_match": random.choice(["matched", "poor_match", "no_match"]),
            }
            events.append(
                RawEvent(
                    raw_event_id=str(uuid.uuid4()),
                    broker_name=self.broker_name,
                    source_id=source_id,
                    timestamp=ts,
                    payload=payload,
                )
            )
        return events
