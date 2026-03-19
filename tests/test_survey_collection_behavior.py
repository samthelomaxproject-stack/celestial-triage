from celestial_triage.ingest.survey_cutouts import ensure_layered_survey_images


def test_existing_panstarrs_still_allows_skyview_collection(monkeypatch):
    monkeypatch.setattr(
        "celestial_triage.ingest.survey_cutouts.fetch_skyview_preview",
        lambda candidate_id, ra, dec, pixels=300: ("https://sv", "/tmp/sv.png"),
    )
    out = ensure_layered_survey_images(
        "cid",
        "sid",
        10.0,
        0.0,
        existing_kinds={"survey_context_panstarrs"},
    )
    assert out["panstarrs"] is None
    assert out["skyview"] is not None
