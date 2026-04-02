from celestial_triage.ingest.antares_api import AntaresApiAdapter
from celestial_triage.ingest.normalizer import normalize_event_safe


class _FakeResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_antares_adapter_maps_locus_payload(monkeypatch):
    def fake_get(*args, **kwargs):
        return _FakeResp(
            200,
            {
                "data": [
                    {
                        "id": "ANT2021abc",
                        "attributes": {
                            "ra": 123.45,
                            "dec": -21.4,
                            "properties": {
                                "newest_alert_id": "ztf:abc:1",
                                "newest_alert_observation_time": 61000.25,
                                "newest_alert_magnitude": 19.2,
                                "num_alerts": 4,
                                "anomaly_type": "rare_transient",
                            },
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr("celestial_triage.ingest.antares_api.requests.get", fake_get)
    adapter = AntaresApiAdapter(limit=5)
    events = adapter.fetch_events()

    assert len(events) == 1
    e = events[0]
    assert e.broker_name == "antares_api"
    assert e.source_id == "ANT2021abc"
    assert e.payload["ra"] == 123.45
    assert e.payload["dec"] == -21.4
    assert e.payload["class_label"] == "rare_transient"

    det, warnings = normalize_event_safe(e)
    assert det is not None
    assert det.broker_name == "antares_api"
    assert det.source_id == "ANT2021abc"
    assert det.ra == 123.45
    assert det.dec == -21.4
    assert det.magnitude == 19.2
    assert isinstance(warnings, list)


def test_antares_adapter_graceful_failure_on_unavailable(monkeypatch):
    def fake_get(*args, **kwargs):
        return _FakeResp(503, {"errors": [{"detail": "service unavailable"}]})

    monkeypatch.setattr("celestial_triage.ingest.antares_api.requests.get", fake_get)
    adapter = AntaresApiAdapter(limit=3)
    assert adapter.fetch_events() == []
