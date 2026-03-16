from abc import ABC, abstractmethod

from celestial_triage.models.entities import RawEvent


class BrokerAdapter(ABC):
    @abstractmethod
    def fetch_events(self) -> list[RawEvent]:
        raise NotImplementedError
