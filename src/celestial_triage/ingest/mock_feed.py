import random
import uuid
from datetime import datetime, timedelta, timezone

from celestial_triage.ingest.base import BrokerAdapter
from celestial_triage.models.entities import RawEvent


class MockFeedAdapter(BrokerAdapter):
    """Mock feed with transparent scenario archetypes for detector validation demos."""

    ARCHETYPES = [
        "inbound_interstellar_like",
        "outbound_hyperbolic_like",
        "slow_persistent_kbo_like",
        "fast_satellite_like",
        "neo_like",
        "ambiguous_anomaly_like",
    ]

    def __init__(self, count: int = 100, broker_name: str = "mock_broker") -> None:
        self.count = count
        self.broker_name = broker_name

    def _payload_for_archetype(self, archetype: str) -> dict:
        if archetype == "inbound_interstellar_like":
            return {
                "ra": random.uniform(0, 360),
                "dec": random.uniform(-70, 70),
                "mag": random.uniform(17, 22),
                "mag_change": random.uniform(-1.2, -0.2),
                "moving": True,
                "class_label": "unknown",
                "class_confidence": random.uniform(0.1, 0.4),
                "catalog_match": random.choice(["no_match", "poor_match"]),
                "mock_archetype_label": archetype,
            }
        if archetype == "outbound_hyperbolic_like":
            return {
                "ra": random.uniform(0, 360),
                "dec": random.uniform(-70, 70),
                "mag": random.uniform(16, 21),
                "mag_change": random.uniform(0.3, 1.4),
                "moving": True,
                "class_label": "unknown",
                "class_confidence": random.uniform(0.1, 0.5),
                "catalog_match": random.choice(["poor_match", "no_match"]),
                "mock_archetype_label": archetype,
            }
        if archetype == "slow_persistent_kbo_like":
            return {
                "ra": random.uniform(0, 360),
                "dec": random.uniform(-20, 20),
                "mag": random.uniform(21, 25),
                "mag_change": random.uniform(-0.2, 0.2),
                "moving": random.random() > 0.45,
                "class_label": "unknown",
                "class_confidence": random.uniform(0.35, 0.65),
                "catalog_match": random.choice(["matched", "poor_match"]),
                "mock_archetype_label": archetype,
            }
        if archetype == "fast_satellite_like":
            return {
                "ra": random.uniform(0, 360),
                "dec": random.uniform(-45, 45),
                "mag": random.uniform(12, 18),
                "mag_change": random.uniform(0.6, 2.2),
                "moving": True,
                "class_label": "artifact",
                "class_confidence": random.uniform(0.1, 0.4),
                "catalog_match": random.choice(["poor_match", "no_match"]),
                "mock_archetype_label": archetype,
            }
        if archetype == "neo_like":
            return {
                "ra": random.uniform(0, 360),
                "dec": random.uniform(-60, 60),
                "mag": random.uniform(16, 21),
                "mag_change": random.uniform(0.2, 1.2),
                "moving": True,
                "class_label": "asteroid",
                "class_confidence": random.uniform(0.45, 0.85),
                "catalog_match": random.choice(["matched", "poor_match"]),
                "mock_archetype_label": archetype,
            }
        return {
            "ra": random.uniform(0, 360),
            "dec": random.uniform(-90, 90),
            "mag": random.uniform(15, 24),
            "mag_change": random.uniform(-2.5, 2.5),
            "moving": random.random() > 0.5,
            "class_label": random.choice(["unknown", "variable"]),
            "class_confidence": random.uniform(0.0, 0.35),
            "catalog_match": random.choice(["matched", "poor_match", "no_match"]),
            "mock_archetype_label": archetype,
        }

    def fetch_events(self) -> list[RawEvent]:
        now = datetime.now(timezone.utc)
        events: list[RawEvent] = []

        source_count = max(12, self.count // 6)
        source_pool = [f"SRC-{i:04d}" for i in range(source_count)]
        source_archetype = {sid: self.ARCHETYPES[i % len(self.ARCHETYPES)] for i, sid in enumerate(source_pool)}

        for _ in range(self.count):
            source_id = random.choice(source_pool)
            archetype = source_archetype[source_id]
            ts = now - timedelta(minutes=random.randint(0, 60 * 24 * 10))
            payload = self._payload_for_archetype(archetype)
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
