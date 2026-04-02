import pytest

from celestial_triage.ingest.antares_api import AntaresApiAdapter
from celestial_triage.ingest.broker_factory import build_broker_adapter
from celestial_triage.ingest.lasair_api import LasairApiAdapter


def test_build_broker_adapter_lasair():
    adapter = build_broker_adapter("lasair", token="tok", lasair_mode="ztf")
    assert isinstance(adapter, LasairApiAdapter)


def test_build_broker_adapter_antares():
    adapter = build_broker_adapter("antares", limit=10)
    assert isinstance(adapter, AntaresApiAdapter)


def test_build_broker_adapter_invalid():
    with pytest.raises(ValueError):
        build_broker_adapter("unknown")
