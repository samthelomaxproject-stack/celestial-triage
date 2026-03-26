from typing import Any


def _classify_kind(name: str) -> str | None:
    n = name.lower()
    if any(k in n for k in ["science", "sci", "new"]):
        return "science"
    if any(k in n for k in ["reference", "template", "ref"]):
        return "reference"
    if any(k in n for k in ["difference", "diff", "sub"]):
        return "difference"
    return None


def _extract_url(value: Any) -> str | None:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    if isinstance(value, dict):
        for k in ("url", "href", "link", "image_url", "cutoutUrl", "stampUrl"):
            v = value.get(k)
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                return v
    return None


def _extract_embedded(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    # Common embedded containers.
    for k in ("base64", "b64", "data", "stampData", "imageData"):
        v = value.get(k)
        if isinstance(v, str) and len(v.strip()) > 20:
            payload_type = "fits_base64" if "fits" in str(value.get("format", "")).lower() else "base64"
            return {
                "payload_type": payload_type,
                k: v,
                "format": value.get("format"),
                "width": value.get("width"),
                "height": value.get("height"),
            }

    # Numeric stamp arrays with shape hints.
    if isinstance(value.get("pixels"), list):
        return {
            "payload_type": "pixel_array",
            "pixels": value.get("pixels"),
            "width": value.get("width"),
            "height": value.get("height"),
        }

    return None


def _classify_from_item_dict(item: dict[str, Any]) -> str | None:
    descriptor = " ".join(
        [
            str(item.get("kind") or ""),
            str(item.get("type") or ""),
            str(item.get("image_type") or ""),
            str(item.get("cutout_type") or ""),
            str(item.get("name") or ""),
            str(item.get("label") or ""),
        ]
    ).strip()
    return _classify_kind(descriptor) if descriptor else None


def extract_image_assets_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract image/cutout references from broker payloads.

    Returns normalized items with keys:
    - kind (science/reference/difference)
    - url (optional)
    - embedded (optional dict)
    - source_field
    - metadata
    """
    found: list[dict[str, Any]] = []

    def add_item(kind: str, source_field: str, url: str | None, embedded: dict[str, Any] | None, metadata: dict[str, Any]) -> None:
        if not url and not embedded:
            return
        found.append(
            {
                "kind": kind,
                "url": url,
                "embedded": embedded,
                "source_field": source_field,
                "metadata": metadata,
            }
        )

    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            # Item-level pattern: {"type": "difference", "url": "..."}
            item_kind = _classify_from_item_dict(obj)
            item_url = _extract_url(obj)
            item_emb = _extract_embedded(obj)
            if item_kind and (item_url or item_emb):
                add_item(
                    kind=item_kind,
                    source_field=path or "item",
                    url=item_url,
                    embedded=item_emb,
                    metadata={"raw_key": "item_type", "typed_item": True},
                )

            for k, v in obj.items():
                p = f"{path}.{k}" if path else k
                kind = _classify_kind(k)
                if kind:
                    add_item(
                        kind=kind,
                        source_field=p,
                        url=_extract_url(v),
                        embedded=_extract_embedded(v),
                        metadata={"raw_key": k},
                    )
                walk(v, p)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(payload)

    # Some brokers provide grouped cutouts.
    cutouts = payload.get("cutouts") if isinstance(payload, dict) else None
    if isinstance(cutouts, dict):
        for key, val in cutouts.items():
            kind = _classify_kind(key)
            if kind:
                add_item(
                    kind=kind,
                    source_field=f"cutouts.{key}",
                    url=_extract_url(val),
                    embedded=_extract_embedded(val),
                    metadata={"cutout_key": key},
                )

    # De-duplicate by kind+url or kind+embedded signature.
    unique: dict[str, dict[str, Any]] = {}
    for item in found:
        url = item.get("url") or ""
        emb = item.get("embedded") or {}
        payload_type = str(emb.get("payload_type") or "")
        sig = f"{item['kind']}|{url}|{item['source_field']}|{payload_type}"
        if sig not in unique:
            unique[sig] = item
    return list(unique.values())
