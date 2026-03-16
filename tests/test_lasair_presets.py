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


def test_cli_lasair_mode_and_base_url_arguments():
    parser = build_parser()
    args = parser.parse_args(
        [
            "ingest-lasair",
            "--lasair-mode",
            "lsst",
            "--base-url",
            "https://lasair.lsst.ac.uk/api",
            "--selected",
            "diaObjectId, ra, decl",
            "--tables",
            "objects",
            "--conditions",
            "1=1",
            "--fetch-cutouts",
        ]
    )
    assert args.lasair_mode == "lsst"
    assert args.base_url == "https://lasair.lsst.ac.uk/api"
    assert args.selected == "diaObjectId, ra, decl"
    assert args.tables == "objects"
    assert args.conditions == "1=1"
    assert args.fetch_cutouts is True


def test_presets_exist_for_required_categories():
    required = {"fast_movers", "iso_candidates", "poor_catalog_matches", "bright_followup", "ambiguous_movers"}
    assert required.issubset(set(PRESETS.keys()))
