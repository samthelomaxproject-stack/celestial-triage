from datetime import datetime, timezone
from pathlib import Path

from celestial_triage.cli import build_export_rows
from celestial_triage.models.entities import NormalizedDetection
from celestial_triage.storage.db import Database


def _det(source_id: str, broker: str, ra: float, dec: float) -> NormalizedDetection:
    return NormalizedDetection(
        detection_id=f"det-{source_id}-{broker}",
        source_id=source_id,
        broker_name=broker,
        timestamp=datetime.now(timezone.utc),
        ra=ra,
        dec=dec,
        magnitude=19.9,
        magnitude_change=0.1,
        moving_flag=False,
        class_label="unknown",
        class_confidence=0.0,
        catalog_match_status="unknown",
        raw_payload_reference=f"raw-{source_id}-{broker}",
        ingest_time=datetime.now(timezone.utc),
    )


def test_provenance_summary_includes_antares(tmp_path: Path):
    db = Database(tmp_path / "prov.db")
    db.init()

    db.insert_detection(_det("ANT2021abc", "antares_api", 12.3, -4.5))
    db.rebuild_candidates_from_detections()

    rows = build_export_rows(db)
    assert rows
    assert any("antares_api:" in str(r.get("provenance_summary") or "") for r in rows)
