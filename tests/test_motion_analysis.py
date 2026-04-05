from datetime import datetime, timedelta, timezone

from celestial_triage.motion.analysis import (
    analyze_candidate_motion,
    angular_separation_arcsec,
)


def _det(ts: datetime, ra: float, dec: float) -> dict:
    return {
        "timestamp": ts.isoformat(),
        "ra": ra,
        "dec": dec,
    }


def test_angular_separation_helper_positive():
    # Small RA shift at equator: 0.001 deg ≈ 3.6 arcsec.
    sep = angular_separation_arcsec(100.0, 0.0, 100.001, 0.0)
    assert 3.5 < sep < 3.7


def test_motion_summary_two_detections():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=30)
    m = analyze_candidate_motion([
        _det(t0, 120.0, -15.0),
        _det(t1, 120.01, -15.0),
    ])
    assert m["detection_count_used"] == 2
    assert m["total_time_span_sec"] == 1800.0
    assert m["angular_displacement_arcsec"] > 0.0
    assert m["average_angular_velocity_arcsec_per_sec"] > 0.0
    assert m["average_position_angle_deg"] is not None
    assert m["motion_state"] in {"stable", "unusual"}


def test_motion_three_detection_consistency_fields_present():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    m = analyze_candidate_motion([
        _det(t0, 200.0, 20.0),
        _det(t0 + timedelta(minutes=20), 200.003, 20.0),
        _det(t0 + timedelta(minutes=40), 200.006, 20.0),
    ])
    assert m["detection_count_used"] == 3
    assert len(m["segment_velocities_arcsec_per_sec"]) >= 2
    assert m["direction_consistency"] is not None
    assert m["motion_consistency_score"] is not None


def test_motion_insufficient_data_graceful():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    m = analyze_candidate_motion([_det(t0, 10.0, -2.0)])
    assert m["detection_count_used"] == 1
    assert m["motion_state"] == "insufficient data"
    assert m["motion_anomaly_flag"] is False


def test_motion_anomaly_score_bounded_and_flag_logic():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Construct a high-motion, inconsistent track.
    m = analyze_candidate_motion([
        _det(t0, 50.0, 0.0),
        _det(t0 + timedelta(minutes=3), 50.02, 0.0),
        _det(t0 + timedelta(minutes=6), 50.02, 0.02),
    ])
    assert 0.0 <= float(m["motion_anomaly_score"]) <= 1.0
    if m["motion_anomaly_score"] >= 0.70:
        assert m["motion_anomaly_flag"] is True
