from datetime import datetime, timezone

from celestial_triage.ingest.normalizer import normalize_event
from celestial_triage.models.entities import RawEvent


def test_normalizer_maps_fields():
    raw = RawEvent(
        raw_event_id="r1",
        broker_name="mock",
        source_id="S1",
        timestamp=datetime.now(timezone.utc),
        payload={
            "ra": 10.5,
            "dec": -4.2,
            "mag": 19.1,
            "mag_change": 0.5,
            "moving": True,
            "class_label": "unknown",
            "class_confidence": 0.4,
            "catalog_match": "no_match",
        },
    )
    d = normalize_event(raw)
    assert d.source_id == "S1"
    assert d.ra == 10.5
    assert d.moving_flag is True
    assert d.catalog_match_status == "no_match"


def test_normalizer_accepts_lsst_decl_field():
    raw = RawEvent(
        raw_event_id="r2",
        broker_name="lasair_api",
        source_id="170032882292621441",
        timestamp=datetime.now(timezone.utc),
        payload={
            "ra": 123.4,
            "decl": -22.5,
        },
    )
    d = normalize_event(raw)
    assert d.ra == 123.4
    assert d.dec == -22.5
