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


def test_lasair_adapter_uses_base_url_override_env(monkeypatch):
    observed: dict[str, object] = {}

    def fake_post(*args, **kwargs):
        observed["url"] = args[0]
        observed["body"] = kwargs.get("json")
        return _FakeResp(200, {"candidates": []})

    monkeypatch.setenv("LASAIR_API_BASE_URL", "https://lasair.lsst.ac.uk/api")
    monkeypatch.setattr("celestial_triage.ingest.lasair_api.requests.post", fake_post)

    adapter = LasairApiAdapter(token="tok", query="objectId:*", limit=5)
    adapter.fetch_events()

    assert observed["url"] == "https://lasair.lsst.ac.uk/api/query/"
    assert "query" in observed["body"]


def test_lasair_adapter_builds_ztf_payload(monkeypatch):
    observed: dict[str, object] = {}

    def fake_post(*args, **kwargs):
        observed["body"] = kwargs.get("json")
        return _FakeResp(200, {"candidates": []})

    monkeypatch.setattr("celestial_triage.ingest.lasair_api.requests.post", fake_post)

    adapter = LasairApiAdapter(
        token="tok",
        lasair_mode="ztf",
        query="is_moving:true",
        limit=7,
        days_back=2,
    )
    adapter.fetch_events()

    body = observed["body"]
    assert body["query"] == "is_moving:true"
    assert body["limit"] == 7
    assert "since" in body


def test_lasair_adapter_builds_lsst_payload(monkeypatch):
    observed: dict[str, object] = {}

    def fake_post(*args, **kwargs):
        observed["body"] = kwargs.get("json")
        return _FakeResp(200, [{"diaObjectId": "170032882292621441", "ra": 123.4, "decl": -22.5}])

    monkeypatch.setattr("celestial_triage.ingest.lasair_api.requests.post", fake_post)

    adapter = LasairApiAdapter(
        token="tok",
        base_url="https://lasair.lsst.ac.uk/api",
        lasair_mode="lsst",
        selected="diaObjectId, ra, decl",
        tables="objects",
        conditions="1=1",
        limit=10,
    )
    events = adapter.fetch_events()

    body = observed["body"]
    assert body == {
        "selected": "diaObjectId, ra, decl",
        "tables": "objects",
        "conditions": "1=1",
    }
    assert len(events) == 1
    assert events[0].source_id == "170032882292621441"
