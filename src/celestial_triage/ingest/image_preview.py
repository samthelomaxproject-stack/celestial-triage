import base64
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image

from celestial_triage.utils.logging import get_logger

LOGGER = get_logger("image_preview")


def _preview_root() -> Path:
    root = (os.getenv("CELESTIAL_TRIAGE_PREVIEW_DIR") or "image_previews").strip()
    p = Path(root)
    if not p.is_absolute():
        p = Path.cwd() / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def _b64_decode(value: str) -> bytes | None:
    s = value.strip()
    if s.startswith("data:") and "," in s:
        s = s.split(",", 1)[1]
    try:
        return base64.b64decode(s, validate=False)
    except Exception:
        return None


def _to_bytes(embedded: dict[str, Any]) -> bytes | None:
    if isinstance(embedded.get("bytes"), (bytes, bytearray)):
        return bytes(embedded["bytes"])

    for k in ("base64", "b64", "data", "stampData", "imageData"):
        v = embedded.get(k)
        if isinstance(v, str):
            decoded = _b64_decode(v)
            if decoded:
                return decoded

    raw = embedded.get("raw")
    if isinstance(raw, str):
        decoded = _b64_decode(raw)
        if decoded:
            return decoded

    return None


def _save_png_from_bytes(data: bytes, out_path: Path) -> bool:
    try:
        img = Image.open(io.BytesIO(data))
        img.save(out_path, format="PNG")
        return True
    except Exception:
        return False


def render_preview_png(
    source_id: str,
    kind: str,
    source_field: str,
    embedded: dict[str, Any],
) -> str | None:
    payload_type = str(embedded.get("payload_type") or "embedded")
    data = _to_bytes(embedded)

    # Optional FITS support if astropy is present.
    if data and payload_type.startswith("fits"):
        try:
            from astropy.io import fits  # type: ignore
            import numpy as np  # type: ignore

            hdul = fits.open(io.BytesIO(data))
            arr = hdul[0].data
            if arr is not None:
                arr = np.nan_to_num(arr)
                arr = arr.astype(float)
                mn, mx = float(arr.min()), float(arr.max())
                if mx > mn:
                    arr = (arr - mn) / (mx - mn)
                arr = (arr * 255).clip(0, 255).astype("uint8")
                img = Image.fromarray(arr)
                root = _preview_root() / source_id
                root.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256((kind + source_field + payload_type).encode()).hexdigest()[:12]
                out_path = root / f"{kind}_{digest}.png"
                if not out_path.exists():
                    img.save(out_path, format="PNG")
                return str(out_path)
        except Exception as exc:
            LOGGER.info("FITS preview render skipped/failed for %s: %s", source_id, exc)

    if not data:
        return None

    root = _preview_root() / source_id
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256((kind + source_field + payload_type + str(len(data))).encode()).hexdigest()[:12]
    out_path = root / f"{kind}_{digest}.png"

    if out_path.exists():
        return str(out_path)

    if _save_png_from_bytes(data, out_path):
        return str(out_path)

    # fallback: if payload includes pixel matrix
    px = embedded.get("pixels")
    w = embedded.get("width")
    h = embedded.get("height")
    try:
        if isinstance(px, list) and isinstance(w, int) and isinstance(h, int) and len(px) == w * h:
            img = Image.new("L", (w, h))
            img.putdata([int(max(0, min(255, p))) for p in px])
            img.save(out_path, format="PNG")
            return str(out_path)
    except Exception:
        pass

    LOGGER.info(
        "Embedded cutout found but preview render failed for source=%s kind=%s field=%s meta=%s",
        source_id,
        kind,
        source_field,
        json.dumps({k: str(type(v).__name__) for k, v in embedded.items()}),
    )
    return None
