import base64
from pathlib import Path

from celestial_triage.ingest.image_assets import extract_image_assets_from_payload
from celestial_triage.ingest.image_preview import render_preview_png


def _tiny_png_b64() -> str:
    # 1x1 transparent PNG
    raw = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return base64.b64encode(raw).decode()


def test_extract_embedded_cutouts_detected():
    payload = {
        "cutouts": {
            "science": {"base64": _tiny_png_b64(), "format": "png"},
            "reference": {"base64": _tiny_png_b64(), "format": "png"},
            "difference": {"base64": _tiny_png_b64(), "format": "png"},
        }
    }
    items = extract_image_assets_from_payload(payload)
    assert len(items) == 3
    assert all(i.get("embedded") for i in items)


def test_render_preview_png_from_embedded_base64(tmp_path, monkeypatch):
    monkeypatch.setenv("CELESTIAL_TRIAGE_PREVIEW_DIR", str(tmp_path))
    embedded = {"payload_type": "base64", "base64": _tiny_png_b64()}
    local = render_preview_png("source1", "science", "cutouts.science", embedded)
    assert local is not None
    assert Path(local).exists()
    assert local.endswith(".png")
