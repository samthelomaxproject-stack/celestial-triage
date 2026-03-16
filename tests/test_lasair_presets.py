from celestial_triage.cli import build_parser
from celestial_triage.ingest.lasair_presets import PRESETS, resolve_preset


def test_resolve_known_preset():
    p = resolve_preset("fast_movers")
    assert p is not None
    assert p.name == "fast_movers"
    assert p.query


def test_cli_preset_argument_mapping():
    parser = build_parser()
    args = parser.parse_args(["ingest-lasair", "--preset", "iso_candidates"])
    assert args.preset == "iso_candidates"
    assert args.cmd == "ingest-lasair"


def test_presets_exist_for_required_categories():
    required = {"fast_movers", "iso_candidates", "poor_catalog_matches", "bright_followup", "ambiguous_movers"}
    assert required.issubset(set(PRESETS.keys()))
