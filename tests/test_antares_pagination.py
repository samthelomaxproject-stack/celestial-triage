from celestial_triage.ingest.antares_api import AntaresApiAdapter


class _Resp:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)

    def json(self):
        return self._payload


def test_antares_fetch_follows_next_links(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(
                {
                    "data": [
                        {
                            "id": "ANTA",
                            "attributes": {
                                "ra": 1.0,
                                "dec": 2.0,
                                "properties": {
                                    "newest_alert_id": "A1",
                                    "newest_alert_observation_time": 61000.0,
                                },
                            },
                        }
                    ],
                    "links": {"next": "https://api.antares.noirlab.edu/v1/loci?page[offset]=10"},
                }
            )
        return _Resp(
            {
                "data": [
                    {
                        "id": "ANTB",
                        "attributes": {
                            "ra": 3.0,
                            "dec": 4.0,
                            "properties": {
                                "newest_alert_id": "B1",
                                "newest_alert_observation_time": 61001.0,
                            },
                        },
                    }
                ],
                "links": {},
            }
        )

    monkeypatch.setattr("celestial_triage.ingest.antares_api.requests.get", fake_get)
    adapter = AntaresApiAdapter(limit=2)
    events = adapter.fetch_events()
    assert len(events) == 2
    assert calls["n"] >= 2
    assert {e.source_id for e in events} == {"ANTA", "ANTB"}
