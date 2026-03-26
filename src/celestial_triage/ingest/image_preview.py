import base64
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
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


def _fits_bytes_to_uint8(data: bytes) -> np.ndarray | None:
    """Minimal FITS primary HDU parser fallback (no astropy dependency)."""
    try:
        i = 0
        header_bytes = b""
        while i + 2880 <= len(data):
            block = data[i : i + 2880]
            header_bytes += block
            i += 2880
            if b"END" in block:
                break
        header_text = header_bytes.decode("ascii", errors="ignore")

        cards = [header_text[j : j + 80] for j in range(0, len(header_text), 80)]
        kv: dict[str, str] = {}
        for c in cards:
            key = c[:8].strip()
            if not key or key == "END" or "=" not in c[:20]:
                continue
            raw = c[10:80].split("/")[0].strip()
            kv[key] = raw

        bitpix = int(kv.get("BITPIX", "-32"))
        naxis = int(kv.get("NAXIS", "0"))
        if naxis < 2:
            return None
        w = int(kv.get("NAXIS1", "0"))
        h = int(kv.get("NAXIS2", "0"))
        if w <= 0 or h <= 0:
            return None

        # Data starts at next 2880 boundary after END card block sequence.
        data_off = ((i + 2879) // 2880) * 2880
        payload = data[data_off:]

        dtype_map = {
            8: ">u1",
            16: ">i2",
            32: ">i4",
            -32: ">f4",
            -64: ">f8",
        }
        dt = dtype_map.get(bitpix)
        if not dt:
            return None

        n = w * h
        arr = np.frombuffer(payload, dtype=np.dtype(dt), count=n)
        if arr.size < n:
            return None
        arr = arr.reshape((h, w))

        # Apply FITS scaling keywords when present.
        bscale = float(kv.get("BSCALE", "1"))
        bzero = float(kv.get("BZERO", "0"))
        arr = arr.astype(float) * bscale + bzero
        arr = np.nan_to_num(arr)

        mn, mx = float(np.min(arr)), float(np.max(arr))
        if mx > mn:
            arr = (arr - mn) / (mx - mn)
        arr = (arr * 255.0).clip(0, 255).astype("uint8")
        return arr
    except Exception:
        return None


def render_preview_png(
    source_id: str,
    kind: str,
    source_field: str,
    embedded: dict[str, Any],
) -> str | None:
    payload_type = str(embedded.get("payload_type") or "embedded")
    data = _to_bytes(embedded)

    # FITS support: astropy when available, otherwise lightweight parser fallback.
    if data and payload_type.startswith("fits"):
        arr = None
        try:
            from astropy.io import fits  # type: ignore

            hdul = fits.open(io.BytesIO(data))
            arr = hdul[0].data
            if arr is not None:
                arr = np.nan_to_num(arr)
                arr = arr.astype(float)
        except Exception:
            arr = _fits_bytes_to_uint8(data)
            if arr is not None:
                img = Image.fromarray(arr)
                root = _preview_root() / source_id
                root.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256((kind + source_field + payload_type).encode()).hexdigest()[:12]
                out_path = root / f"{kind}_{digest}.png"
                if not out_path.exists():
                    img.save(out_path, format="PNG")
                return str(out_path)

        if arr is not None:
            mn, mx = float(np.min(arr)), float(np.max(arr))
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

        LOGGER.info("FITS preview render skipped/failed for %s", source_id)

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
