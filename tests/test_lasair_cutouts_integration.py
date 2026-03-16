from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from celestial_triage.cli import cmd_ingest_lasair
from celestial_triage.models.entities import RawEvent
from celestial_triage.storage.db import Database


def test_ingest_lasair_fetch_cutouts_populates_image_assets(monkeypatch, tmp_path):
    db_path = tmp_path / "ct.db"
    monkeypatch.setattr("celestial_triage.cli.DB_PATH", db_path)

    raw = RawEvent(
        raw_event_id="raw-1",
        broker_name="lasair_api",
        source_id="1700",
        timestamp=datetime.now(timezone.utc),
        payload={
            "diaObjectId": "1700",
            "ra": 123.4,
            "decl": -22.5,
            "midpointMjdTai": 61000.0,
        },
    )

    monkeypatch.setattr("celestial_triage.ingest.lasair_api.LasairApiAdapter.fetch_events", lambda self: [raw])
    monkeypatch.setattr(
        "celestial_triage.ingest.lasair_api.LasairApiAdapter.fetch_object_detail",
        lambda self, source_id: {
            "cutouts": {
                "science": {"url": "https://example.org/science.png"},
                "reference": {"url": "https://example.org/reference.png"},
                "difference": {"url": "https://example.org/difference.png"},
            }
        },
    )

    args = SimpleNamespace(
        token="tok",
        query="",
        limit=5,
        days_back=1,
        base_url="https://lasair.lsst.ac.uk/api",
        lasair_mode="lsst",
        selected="diaObjectId, ra, decl",
        tables="objects",
        conditions="1=1",
        preset=None,
        fetch_cutouts=True,
    )

    cmd_ingest_lasair(args)

    db = Database(db_path)
    cids = db.list_candidate_ids()
    assert len(cids) == 1
    images = db.get_images_for_candidate(cids[0])
    kinds = {i["kind"] for i in images}
    assert {"science", "reference", "difference"}.issubset(kinds)
