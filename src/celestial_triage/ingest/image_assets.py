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
        for k in ("url", "href", "link"):
            v = value.get(k)
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                return v
    return None


def extract_image_assets_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract image/cutout references from broker payloads.

    Returns normalized items with keys: kind, url, source_field, metadata.
    """
    found: list[dict[str, Any]] = []

    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else k
                kind = _classify_kind(k)
                url = _extract_url(v)
                if kind and url:
                    found.append(
                        {
                            "kind": kind,
                            "url": url,
                            "source_field": p,
                            "metadata": {"raw_key": k},
                        }
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
            url = _extract_url(val)
            if kind and url:
                found.append(
                    {
                        "kind": kind,
                        "url": url,
                        "source_field": f"cutouts.{key}",
                        "metadata": {"cutout_key": key},
                    }
                )

    # De-duplicate by (kind, url).
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in found:
        key = (item["kind"], item["url"])
        if key not in unique:
            unique[key] = item
    return list(unique.values())
