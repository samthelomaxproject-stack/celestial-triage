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
        "limit": 10,
    }
    assert len(events) == 1
    assert events[0].source_id == "170032882292621441"


def test_lasair_object_detail_get_path(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, **kwargs):
        calls["n"] += 1
        if url.endswith("/object/1700/"):
            return _FakeResp(200, {"cutouts": {"science": {"url": "https://img/science.png"}}})
        return _FakeResp(404, {"detail": "not found"})

    monkeypatch.setattr("celestial_triage.ingest.lasair_api.requests.get", fake_get)
    adapter = LasairApiAdapter(token="tok", base_url="https://lasair.lsst.ac.uk/api", lasair_mode="lsst")
    detail = adapter.fetch_object_detail("1700")
    assert detail is not None
    assert "cutouts" in detail
    assert calls["n"] >= 1


def test_lasair_object_detail_lsst_query_fallback(monkeypatch):
    def fake_get(*args, **kwargs):
        return _FakeResp(404, {"detail": "not found"})

    observed = {"body": None}

    def fake_post(url, **kwargs):
        observed["body"] = kwargs.get("json")
        return _FakeResp(200, [{"diaObjectId": "1700", "cutouts": {"difference": {"url": "https://img/diff.png"}}}])

    monkeypatch.setattr("celestial_triage.ingest.lasair_api.requests.get", fake_get)
    monkeypatch.setattr("celestial_triage.ingest.lasair_api.requests.post", fake_post)

    adapter = LasairApiAdapter(token="tok", base_url="https://lasair.lsst.ac.uk/api", lasair_mode="lsst")
    detail = adapter.fetch_object_detail("1700")
    assert detail is not None
    assert detail.get("diaObjectId") == "1700"
    assert observed["body"]["conditions"] == "diaObjectId='1700'"


def test_lasair_batched_fetch_respects_total_limit(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        body = kwargs.get("json") or {}
        lim = int(body.get("limit") or 0)
        rows = [
            {
                "diaObjectId": f"{calls['n']}-{i}",
                "midpointMjdTai": 61000.0 + i,
            }
            for i in range(lim)
        ]
        return _FakeResp(200, rows)

    monkeypatch.setattr("celestial_triage.ingest.lasair_api.requests.post", fake_post)
    monkeypatch.setattr("celestial_triage.ingest.lasair_api.time.sleep", lambda *_: None)

    adapter = LasairApiAdapter(token="tok", lasair_mode="lsst", limit=12, batch_size=5, request_delay=0)
    events = adapter.fetch_events()
    assert len(events) == 12
    assert calls["n"] == 3


def test_lasair_backoff_retries_on_429(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            return _FakeResp(429, {"detail": "rate limit"})
        return _FakeResp(200, [{"diaObjectId": "ok-1", "midpointMjdTai": 61000.0}])

    sleeps = []
    monkeypatch.setattr("celestial_triage.ingest.lasair_api.requests.post", fake_post)
    monkeypatch.setattr("celestial_triage.ingest.lasair_api.time.sleep", lambda s: sleeps.append(s))

    adapter = LasairApiAdapter(token="tok", lasair_mode="lsst", limit=1, batch_size=1, request_delay=1, max_retries=3)
    events = adapter.fetch_events()
    assert len(events) == 1
    assert calls["n"] == 3
    assert sleeps[:2] == [1.0, 2.0]
