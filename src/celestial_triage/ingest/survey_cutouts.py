from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import requests

from celestial_triage.utils.logging import get_logger

LOGGER = get_logger("survey_cutouts")


def _preview_root() -> Path:
    root = (os.getenv("CELESTIAL_TRIAGE_PREVIEW_DIR") or "image_previews").strip()
    p = Path(root)
    if not p.is_absolute():
        p = Path.cwd() / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_bytes(path: Path, content: bytes) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return True
    except Exception:
        return False


def panstarrs_cutout_url(ra: float, dec: float, size: int = 240) -> str:
    return f"https://ps1images.stsci.edu/cgi-bin/fitscut.cgi?ra={ra}&dec={dec}&size={size}&format=png"


def fetch_panstarrs_preview(candidate_id: str, ra: float, dec: float, size: int = 240) -> tuple[str, str | None]:
    url = panstarrs_cutout_url(ra, dec, size=size)
    out = _preview_root() / str(candidate_id) / "survey_context_panstarrs.png"
    if out.exists():
        return url, str(out)

    try:
        r = requests.get(url, timeout=20)
    except requests.RequestException as exc:
        LOGGER.info("Pan-STARRS request failed for %s: %s", candidate_id, exc)
        return url, None

    ctype = (r.headers.get("content-type") or "").lower()
    if r.status_code >= 400 or "image" not in ctype:
        return url, None

    if _save_bytes(out, r.content):
        return url, str(out)
    return url, None


def _extract_png_link(html: str) -> str | None:
    m = re.search(r"(https?://[^\"'\s>]+\.png(?:\?[^\"'\s>]*)?)", html, flags=re.IGNORECASE)
    return m.group(1) if m else None


def fetch_skyview_preview(candidate_id: str, ra: float, dec: float, pixels: int = 300) -> tuple[str, str | None]:
    base = "https://skyview.gsfc.nasa.gov/current/cgi/runquery.pl"
    params = {
        "Position": f"{ra},{dec}",
        "Survey": "DSS",
        "Coordinates": "J2000",
        "Projection": "Tan",
        "Pixels": str(pixels),
        "Return": "PNG",
    }
    request_url = f"{base}?Position={ra},{dec}&Survey=DSS&Pixels={pixels}&Return=PNG"
    out = _preview_root() / str(candidate_id) / "survey_context_skyview.png"
    if out.exists():
        return request_url, str(out)

    try:
        r = requests.get(base, params=params, timeout=30)
    except requests.RequestException as exc:
        LOGGER.info("SkyView request failed for %s: %s", candidate_id, exc)
        return request_url, None

    ctype = (r.headers.get("content-type") or "").lower()
    if r.status_code < 400 and "image" in ctype:
        if _save_bytes(out, r.content):
            return request_url, str(out)
        return request_url, None

    # If HTML result, attempt to find PNG link and fetch it.
    png_link = _extract_png_link(r.text)
    if not png_link:
        return request_url, None
    try:
        pr = requests.get(png_link, timeout=30)
        ptype = (pr.headers.get("content-type") or "").lower()
        if pr.status_code < 400 and "image" in ptype and _save_bytes(out, pr.content):
            return png_link, str(out)
    except requests.RequestException:
        return request_url, None

    return request_url, None


def ensure_layered_survey_images(
    candidate_id: str,
    source_id: str,
    ra: float,
    dec: float,
    existing_kinds: set[str] | None = None,
) -> dict[str, Any]:
    existing_kinds = existing_kinds or set()
    result: dict[str, Any] = {
        "candidate_id": candidate_id,
        "source_id": source_id,
        "panstarrs": None,
        "skyview": None,
    }

    # Broker images are already stored separately; do not replace them.
    if "survey_context_panstarrs" not in existing_kinds:
        p_url, p_local = fetch_panstarrs_preview(candidate_id, ra, dec)
        if p_local:
            result["panstarrs"] = {"remote_url": p_url, "local_path": p_local, "kind": "survey_context_panstarrs"}

    # Fallback only if Pan-STARRS unavailable.
    if "survey_context_skyview" not in existing_kinds and result["panstarrs"] is None:
        s_url, s_local = fetch_skyview_preview(candidate_id, ra, dec)
        if s_local:
            result["skyview"] = {"remote_url": s_url, "local_path": s_local, "kind": "survey_context_skyview"}

    return result
