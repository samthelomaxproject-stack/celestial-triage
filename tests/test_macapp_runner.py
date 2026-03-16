from celestial_triage.macapp.runner import APPROVED_COMMANDS, SafeCliRunner


def test_runner_rejects_unapproved_command():
    r = SafeCliRunner()
    try:
        r.build_args("rm -rf /", {})
        assert False, "expected ValueError"
    except ValueError:
        assert True


def test_runner_builds_ingest_lasair_args_safely():
    r = SafeCliRunner()
    args = r.build_args(
        "ingest-lasair",
        {
            "lasair_mode": "lsst",
            "base_url": "https://lasair.lsst.ac.uk/api",
            "selected": "diaObjectId, ra, decl",
            "tables": "objects",
            "conditions": "1=1",
            "limit": 10,
        },
    )
    s = " ".join(args)
    assert "celestial_triage.cli ingest-lasair" in s
    assert "--lasair-mode lsst" in s
    assert "--base-url https://lasair.lsst.ac.uk/api" in s
    assert "--selected diaObjectId, ra, decl" in s


def test_approved_commands_match_required_surface():
    required = {
        "init-db",
        "seed-mock",
        "ingest-jsonl",
        "ingest-lasair",
        "run-pipeline",
        "top-candidates",
        "scenario-report",
        "update-review",
        "followup-report",
        "export-candidates",
        "bundle-cases",
    }
    assert required.issubset(APPROVED_COMMANDS)
