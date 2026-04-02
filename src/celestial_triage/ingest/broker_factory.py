from __future__ import annotations

from typing import Any

from celestial_triage.ingest.antares_api import AntaresApiAdapter
from celestial_triage.ingest.base import BrokerAdapter
from celestial_triage.ingest.lasair_api import LasairApiAdapter


def build_broker_adapter(broker: str, **kwargs: Any) -> BrokerAdapter:
    name = (broker or "").strip().lower()
    if name == "lasair":
        return LasairApiAdapter(**kwargs)
    if name == "antares":
        return AntaresApiAdapter(**kwargs)
    raise ValueError(f"Unsupported broker adapter: {broker}")
