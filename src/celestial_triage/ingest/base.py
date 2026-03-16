from abc import ABC, abstractmethod

from celestial_triage.models.entities import RawEvent

REQUIRED_NORMALIZED_FIELDS = [
    "detection_id",
    "source_id",
    "broker_name",
    "timestamp",
    "ra",
    "dec",
    "magnitude",
    "magnitude_change",
    "moving_flag",
    "class_label",
    "class_confidence",
    "catalog_match_status",
    "raw_payload_reference",
    "ingest_time",
]


class BrokerAdapter(ABC):
    """Broker adapter contract.

    Adapters fetch raw broker events. Normalization is handled separately.
    Implementations should provide stable `source_id` values so detections can
    be linked into candidate histories/tracks.
    """

    @abstractmethod
    def fetch_events(self) -> list[RawEvent]:
        raise NotImplementedError
