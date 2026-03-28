from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ObserverLocation:
    latitude_deg: float
    longitude_deg: float
    elevation_m: float = 0.0


@dataclass
class TelescopePointing:
    mode: str  # "radec" | "altaz"
    ra_deg: float | None = None
    dec_deg: float | None = None
    alt_deg: float | None = None
    az_deg: float | None = None
    fov_deg: float = 2.0
    min_alt_deg: float = 20.0


@dataclass
class ObservabilityResult:
    alt_deg: float
    az_deg: float
    visible_now: bool
    status: str
    in_fov: bool
    separation_deg: float | None


def _to_rad(deg: float) -> float:
    return math.radians(float(deg))


def _to_deg(rad: float) -> float:
    return math.degrees(float(rad))


def _julian_date(dt_utc: datetime) -> float:
    dt = dt_utc.astimezone(timezone.utc)
    year = dt.year
    month = dt.month
    day = dt.day + (dt.hour + dt.minute / 60.0 + dt.second / 3600.0) / 24.0
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + (a // 4)
    jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + b - 1524.5
    return float(jd)


def _gmst_rad(dt_utc: datetime) -> float:
    jd = _julian_date(dt_utc)
    t = (jd - 2451545.0) / 36525.0
    gmst_deg = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * (t**2)
        - (t**3) / 38710000.0
    )
    return _to_rad(gmst_deg % 360.0)


def _normalize_angle_rad(x: float) -> float:
    y = x % (2.0 * math.pi)
    return y


def radec_to_altaz(
    ra_deg: float,
    dec_deg: float,
    observer: ObserverLocation,
    when_utc: datetime | None = None,
) -> tuple[float, float]:
    now = when_utc or datetime.now(timezone.utc)
    ra = _to_rad(ra_deg)
    dec = _to_rad(dec_deg)
    lat = _to_rad(observer.latitude_deg)
    lon = _to_rad(observer.longitude_deg)

    lst = _normalize_angle_rad(_gmst_rad(now) + lon)
    ha = lst - ra

    sin_alt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(ha)
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.asin(sin_alt)

    cos_alt = max(1e-12, math.cos(alt))
    sin_az = -math.sin(ha) * math.cos(dec) / cos_alt
    cos_az = (math.sin(dec) - math.sin(alt) * math.sin(lat)) / (cos_alt * max(1e-12, math.cos(lat)))
    az = math.atan2(sin_az, cos_az)
    az = _normalize_angle_rad(az)

    return (_to_deg(alt), _to_deg(az))


def altaz_to_radec(
    alt_deg: float,
    az_deg: float,
    observer: ObserverLocation,
    when_utc: datetime | None = None,
) -> tuple[float, float]:
    now = when_utc or datetime.now(timezone.utc)
    alt = _to_rad(alt_deg)
    az = _to_rad(az_deg)
    lat = _to_rad(observer.latitude_deg)
    lon = _to_rad(observer.longitude_deg)

    sin_dec = math.sin(alt) * math.sin(lat) + math.cos(alt) * math.cos(lat) * math.cos(az)
    sin_dec = max(-1.0, min(1.0, sin_dec))
    dec = math.asin(sin_dec)

    cos_dec = max(1e-12, math.cos(dec))
    sin_ha = -math.sin(az) * math.cos(alt) / cos_dec
    cos_ha = (math.sin(alt) - math.sin(lat) * math.sin(dec)) / (max(1e-12, math.cos(lat)) * cos_dec)
    ha = math.atan2(sin_ha, cos_ha)

    lst = _normalize_angle_rad(_gmst_rad(now) + lon)
    ra = _normalize_angle_rad(lst - ha)

    return (_to_deg(ra), _to_deg(dec))


def angular_separation_deg(ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float) -> float:
    ra1 = _to_rad(ra1_deg)
    dec1 = _to_rad(dec1_deg)
    ra2 = _to_rad(ra2_deg)
    dec2 = _to_rad(dec2_deg)
    cos_sep = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    cos_sep = max(-1.0, min(1.0, cos_sep))
    return _to_deg(math.acos(cos_sep))


def evaluate_observability(
    ra_deg: float,
    dec_deg: float,
    observer: ObserverLocation,
    telescope: TelescopePointing | None,
    when_utc: datetime | None = None,
) -> ObservabilityResult:
    alt, az = radec_to_altaz(ra_deg, dec_deg, observer, when_utc=when_utc)

    if alt < 0:
        status = "below horizon"
    elif alt < 15:
        status = "low on horizon"
    else:
        status = "visible now"

    min_alt = telescope.min_alt_deg if telescope else 0.0
    visible_now = alt >= max(0.0, float(min_alt))

    separation = None
    in_fov = False
    if telescope is not None:
        if telescope.mode == "altaz" and telescope.alt_deg is not None and telescope.az_deg is not None:
            tra, tdec = altaz_to_radec(telescope.alt_deg, telescope.az_deg, observer, when_utc=when_utc)
        else:
            tra = telescope.ra_deg
            tdec = telescope.dec_deg

        if tra is not None and tdec is not None:
            separation = angular_separation_deg(ra_deg, dec_deg, float(tra), float(tdec))
            in_fov = separation <= max(0.0, float(telescope.fov_deg) / 2.0)

    return ObservabilityResult(
        alt_deg=alt,
        az_deg=az,
        visible_now=bool(visible_now),
        status=status,
        in_fov=bool(in_fov),
        separation_deg=separation,
    )
