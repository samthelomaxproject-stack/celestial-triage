from celestial_triage.ingest.lasair_api import LasairApiAdapter


class _FakeResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_lasair_adapter_parses_candidates_payload(monkeypatch):
    def fake_post(*args, **kwargs):
        return _FakeResp(
            200,
            {
                "candidates": [
                    {
                        "objectId": "ZTF-test-1",
                        "candid": "123",
                        "timestamp": "2026-03-15T00:00:00+00:00",
                        "ra": 10.1,
                        "dec": -1.2,
                        "magpsf": 19.4,
                    }
                ]
            },
        )

    monkeypatch.setattr("celestial_triage.ingest.lasair_api.requests.post", fake_post)
    adapter = LasairApiAdapter(token="tok", limit=5)
    events = adapter.fetch_events()
    assert len(events) == 1
    assert events[0].source_id == "ZTF-test-1"


def test_lasair_adapter_handles_rate_limit(monkeypatch):
    def fake_post(*args, **kwargs):
        return _FakeResp(429, {"error": "rate limit"})

    monkeypatch.setattr("celestial_triage.ingest.lasair_api.requests.post", fake_post)
    adapter = LasairApiAdapter(token="tok", limit=5)
    events = adapter.fetch_events()
    assert events == []
