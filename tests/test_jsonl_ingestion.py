from pathlib import Path

from celestial_triage.ingest.external_jsonl import JsonlExternalAdapter
from celestial_triage.ingest.normalizer import normalize_event_safe


def test_jsonl_adapter_handles_malformed_and_missing_source(tmp_path: Path):
    p = tmp_path / "in.jsonl"
    p.write_text(
        "\n".join(
            [
                '{"source_id":"A","timestamp":"2026-03-15T00:00:00+00:00","ra":10.0,"dec":5.0}',
                "not-json-line",
                '{"timestamp":"2026-03-15T00:00:00+00:00","ra":10.0,"dec":5.0}',
                '{"objectId":"B","timestamp":"2026-03-15T00:10:00+00:00","ra":11.0,"dec":6.0}',
            ]
        )
    )
    events = JsonlExternalAdapter(p).fetch_events()
    assert len(events) == 2  # one malformed + one missing source id should be skipped


def test_normalizer_partial_record_fallbacks():
    from datetime import datetime, timezone

    from celestial_triage.models.entities import RawEvent

    raw = RawEvent(
        raw_event_id="r1",
        broker_name="external_jsonl",
        source_id="X",
        timestamp=datetime.now(timezone.utc),
        payload={
            "ra_deg": 100.1,
            "dec_deg": -20.2,
            "magpsf": 21.0,
            "is_moving": "true",
            "match_status": "no_match",
        },
    )
    det, warnings = normalize_event_safe(raw)
    assert det is not None
    assert det.ra == 100.1
    assert det.dec == -20.2
    assert det.magnitude == 21.0
    assert det.moving_flag is True
    assert isinstance(warnings, list)
