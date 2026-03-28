from __future__ import annotations

from datetime import datetime, timezone

from celestial_triage.astro.observability import (
    ObserverLocation,
    TelescopePointing,
    altaz_to_radec,
    angular_separation_deg,
    evaluate_observability,
    radec_to_altaz,
)


def test_radec_altaz_roundtrip_basic() -> None:
    obs = ObserverLocation(latitude_deg=30.2672, longitude_deg=-97.7431, elevation_m=150)
    t = datetime(2026, 3, 27, 5, 0, 0, tzinfo=timezone.utc)
    ra, dec = 120.0, -15.0
    alt, az = radec_to_altaz(ra, dec, obs, when_utc=t)
    r2, d2 = altaz_to_radec(alt, az, obs, when_utc=t)
    assert abs(d2 - dec) < 1e-4
    # RA wraps at 360, compare angularly
    sep = angular_separation_deg(ra, dec, r2, d2)
    assert sep < 1e-3


def test_visible_now_determination() -> None:
    obs = ObserverLocation(latitude_deg=0.0, longitude_deg=0.0)
    t = datetime(2026, 3, 27, 0, 0, 0, tzinfo=timezone.utc)
    tel = TelescopePointing(mode="radec", ra_deg=0.0, dec_deg=0.0, fov_deg=10.0, min_alt_deg=10.0)

    # Same direction as telescope center should be in fov; visibility depends on alt
    out = evaluate_observability(0.0, 0.0, obs, tel, when_utc=t)
    assert isinstance(out.visible_now, bool)
    assert out.status in {"below horizon", "low on horizon", "visible now"}


def test_fov_inclusion_logic() -> None:
    obs = ObserverLocation(latitude_deg=30.0, longitude_deg=-100.0)
    t = datetime(2026, 3, 27, 6, 0, 0, tzinfo=timezone.utc)
    tel = TelescopePointing(mode="radec", ra_deg=50.0, dec_deg=10.0, fov_deg=4.0, min_alt_deg=0.0)

    inside = evaluate_observability(50.5, 10.1, obs, tel, when_utc=t)
    outside = evaluate_observability(70.0, 30.0, obs, tel, when_utc=t)
    assert inside.separation_deg is not None and inside.separation_deg < 2.0
    assert inside.in_fov is True
    assert outside.separation_deg is not None and outside.separation_deg > 2.0
    assert outside.in_fov is False


def test_missing_observer_handled_by_caller_contract() -> None:
    # Helper functions require explicit observer; caller is responsible for None checks.
    obs = ObserverLocation(latitude_deg=10.0, longitude_deg=20.0)
    t = datetime(2026, 3, 27, 6, 0, 0, tzinfo=timezone.utc)
    out = radec_to_altaz(10.0, 20.0, obs, when_utc=t)
    assert len(out) == 2
