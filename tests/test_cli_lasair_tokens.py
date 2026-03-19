from celestial_triage.cli import _resolve_lasair_token


def test_resolve_lasair_token_prefers_cli_token(monkeypatch):
    monkeypatch.setenv("LASAIR_LSST_API_TOKEN", "env-lsst")
    assert _resolve_lasair_token("lsst", "cli-token") == "cli-token"


def test_resolve_lasair_token_uses_mode_specific_env(monkeypatch):
    monkeypatch.setenv("LASAIR_LSST_API_TOKEN", "env-lsst")
    monkeypatch.setenv("LASAIR_ZTF_API_TOKEN", "env-ztf")

    assert _resolve_lasair_token("lsst", None) == "env-lsst"
    assert _resolve_lasair_token("ztf", None) == "env-ztf"
