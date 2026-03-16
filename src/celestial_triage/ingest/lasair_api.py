import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from celestial_triage.ingest.base import BrokerAdapter
from celestial_triage.models.entities import RawEvent
from celestial_triage.utils.logging import get_logger

LOGGER = get_logger("lasair_api")


class LasairApiAdapter(BrokerAdapter):
    """Minimal Lasair REST adapter.

    Notes:
    - Keeps architecture broker-agnostic by returning RawEvent only.
    - Uses tolerant field extraction to support changing payload variants.
    """

    def __init__(
        self,
        token: str | None = None,
        query: str = "objectId:*",
        limit: int = 100,
        days_back: int = 3,
        base_url: str = "https://lasair-ztf.lsst.ac.uk/api",
    ) -> None:
        self.token = token or os.getenv("LASAIR_API_TOKEN", "")
        self.query = query
        self.limit = max(1, min(1000, int(limit)))
        self.days_back = max(1, min(30, int(days_back)))
        self.base_url = base_url.rstrip("/")

    def _extract_list(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            for key in ("candidates", "results", "items", "objects", "alerts"):
                v = payload.get(key)
                if isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
            return []
        return []

    def _extract_timestamp(self, row: dict[str, Any]) -> datetime:
        candidates = [
            row.get("timestamp"),
            row.get("utc"),
            row.get("jd"),
            row.get("mjd"),
            row.get("obstime"),
        ]
        for v in candidates:
            if v is None:
                continue
            if isinstance(v, (int, float)):
                # treat numeric as unix seconds fallback
                try:
                    return datetime.fromtimestamp(float(v), tz=timezone.utc)
                except Exception:
                    continue
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except Exception:
                continue
        return datetime.now(timezone.utc)

    def fetch_events(self) -> list[RawEvent]:
        if not self.token:
            LOGGER.warning("LASAIR_API_TOKEN missing; skipping live Lasair ingestion")
            return []

        # Use watch endpoint style payload, with query and lookback hints.
        since = (datetime.now(timezone.utc) - timedelta(days=self.days_back)).isoformat()
        url = f"{self.base_url}/query"
        headers = {"Authorization": f"Token {self.token}", "Content-Type": "application/json"}
        body = {
            "query": self.query,
            "limit": self.limit,
            "since": since,
        }

        try:
            resp = requests.post(url, json=body, headers=headers, timeout=30)
        except requests.RequestException as exc:
            LOGGER.error("Lasair request failed: %s", exc)
            return []

        if resp.status_code in (401, 403):
            LOGGER.error("Lasair auth/permission error: HTTP %s", resp.status_code)
            return []
        if resp.status_code == 429:
            LOGGER.warning("Lasair rate limited (HTTP 429). Try again later.")
            return []
        if resp.status_code >= 400:
            LOGGER.error("Lasair API error HTTP %s: %s", resp.status_code, resp.text[:200])
            return []

        try:
            payload = resp.json()
        except ValueError:
            LOGGER.error("Lasair API returned non-JSON payload")
            return []

        rows = self._extract_list(payload)
        events: list[RawEvent] = []
        for row in rows:
            source_id = str(row.get("source_id") or row.get("objectId") or row.get("oid") or "")
            if not source_id:
                LOGGER.warning("Skipping Lasair row without source id")
                continue
            ts = self._extract_timestamp(row)
            raw_event_id = str(row.get("raw_event_id") or row.get("candid") or f"{source_id}-{ts.isoformat()}")
            events.append(
                RawEvent(
                    raw_event_id=raw_event_id,
                    broker_name="lasair_api",
                    source_id=source_id,
                    timestamp=ts,
                    payload=row,
                )
            )

        LOGGER.info("Fetched %d Lasair raw events", len(events))
        return events
