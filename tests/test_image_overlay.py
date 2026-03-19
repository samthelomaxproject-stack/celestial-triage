from celestial_triage.ui.image_overlay import build_track_offsets, format_radec_overlay


def test_format_radec_overlay_compact():
    txt = format_radec_overlay(53.090601596, -29.651903404)
    assert txt is not None
    assert "RA" in txt and "DEC" in txt


def test_track_offsets_empty_for_single_detection():
    dets = [{"timestamp": "2026-03-01T00:00:00+00:00", "ra": 10.0, "dec": 20.0}]
    out = build_track_offsets(dets, 10.0, 20.0)
    assert out == []


def test_track_offsets_multiple_detections_sorted_and_scaled():
    dets = [
        {"timestamp": "2026-03-01T00:00:02+00:00", "ra": 10.0003, "dec": 20.0002},
        {"timestamp": "2026-03-01T00:00:01+00:00", "ra": 10.0001, "dec": 20.0001},
        {"timestamp": "2026-03-01T00:00:03+00:00", "ra": 10.0005, "dec": 20.0003},
    ]
    out = build_track_offsets(dets, 10.0, 20.0, max_radius_px=20.0)
    assert len(out) == 3
    # should trend rightward with increasing RA over time
    assert out[0][0] < out[1][0] < out[2][0]


def test_track_offsets_skip_missing_coords():
    dets = [
        {"timestamp": "2026-03-01T00:00:00+00:00", "ra": None, "dec": 20.0},
        {"timestamp": "2026-03-01T00:00:01+00:00", "ra": 10.1, "dec": 20.1},
        {"timestamp": "2026-03-01T00:00:02+00:00", "ra": 10.2, "dec": 20.2},
    ]
    out = build_track_offsets(dets, 10.0, 20.0)
    assert len(out) == 2
