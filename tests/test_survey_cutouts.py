from pathlib import Path

from celestial_triage.ingest import survey_cutouts


class _Resp:
    def __init__(self, status_code=200, content=b"", text="", headers=None):
        self.status_code = status_code
        self.content = content
        self.text = text
        self.headers = headers or {}


def test_panstarrs_fetch_saves_png(monkeypatch, tmp_path):
    monkeypatch.setenv("CELESTIAL_TRIAGE_PREVIEW_DIR", str(tmp_path))

    def fake_get(url, timeout=20):
        return _Resp(200, content=b"PNGDATA", headers={"content-type": "image/png"})

    monkeypatch.setattr("celestial_triage.ingest.survey_cutouts.requests.get", fake_get)
    remote, local = survey_cutouts.fetch_panstarrs_preview("c1", 10.0, -1.0)
    assert "ps1images.stsci.edu" in remote
    assert local is not None
    assert Path(local).exists()


def test_skyview_fallback_uses_html_png_link(monkeypatch, tmp_path):
    monkeypatch.setenv("CELESTIAL_TRIAGE_PREVIEW_DIR", str(tmp_path))

    calls = {"n": 0}

    def fake_get(url, params=None, timeout=30):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(200, text="<a href='https://example.org/sky.png'>img</a>", headers={"content-type": "text/html"})
        return _Resp(200, content=b"PNGDATA2", headers={"content-type": "image/png"})

    monkeypatch.setattr("celestial_triage.ingest.survey_cutouts.requests.get", fake_get)
    remote, local = survey_cutouts.fetch_skyview_preview("c2", 11.0, 5.0)
    assert remote
    assert local is not None
    assert Path(local).exists()


def test_priority_prefers_panstarrs_over_skyview(monkeypatch):
    monkeypatch.setattr(
        "celestial_triage.ingest.survey_cutouts.fetch_panstarrs_preview",
        lambda candidate_id, ra, dec, size=240: ("https://ps", "/tmp/pan.png"),
    )
    monkeypatch.setattr(
        "celestial_triage.ingest.survey_cutouts.fetch_skyview_preview",
        lambda candidate_id, ra, dec, pixels=300: ("https://sv", "/tmp/sv.png"),
    )
    out = survey_cutouts.ensure_layered_survey_images("cid", "sid", 10.0, 0.0, existing_kinds=set())
    assert out["panstarrs"] is not None
    assert out["skyview"] is None


def test_priority_uses_skyview_when_panstarrs_missing(monkeypatch):
    monkeypatch.setattr(
        "celestial_triage.ingest.survey_cutouts.fetch_panstarrs_preview",
        lambda candidate_id, ra, dec, size=240: ("https://ps", None),
    )
    monkeypatch.setattr(
        "celestial_triage.ingest.survey_cutouts.fetch_skyview_preview",
        lambda candidate_id, ra, dec, pixels=300: ("https://sv", "/tmp/sv.png"),
    )
    out = survey_cutouts.ensure_layered_survey_images("cid", "sid", 10.0, 0.0, existing_kinds=set())
    assert out["panstarrs"] is None
    assert out["skyview"] is not None
