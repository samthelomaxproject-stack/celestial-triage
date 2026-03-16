import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import requests

from celestial_triage.ingest.base import BrokerAdapter
from celestial_triage.models.entities import RawEvent
from celestial_triage.utils.logging import get_logger

LOGGER = get_logger("lasair_api")


class LasairApiAdapter(BrokerAdapter):
    """Minimal Lasair REST adapter.

    Supports two query modes:
    - ztf: query-string style payload (``{"query": "..."}``)
    - lsst: selected/tables/conditions payload

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
        base_url: str | None = None,
        lasair_mode: str = "ztf",
        selected: str = "",
        tables: str = "",
        conditions: str = "",
    ) -> None:
        self.token = token or os.getenv("LASAIR_API_TOKEN", "")
        self.query = query
        self.limit = max(1, min(1000, int(limit)))
        self.days_back = max(1, min(30, int(days_back)))
        env_base_url = os.getenv("LASAIR_API_BASE_URL", "").strip()
        resolved_base = base_url or env_base_url or "https://lasair-ztf.lsst.ac.uk/api"
        self.base_url = resolved_base.rstrip("/")
        self.lasair_mode = (lasair_mode or "ztf").strip().lower()
        if self.lasair_mode not in {"ztf", "lsst"}:
            raise ValueError("lasair_mode must be one of: ztf, lsst")
        self.selected = selected.strip()
        self.tables = tables.strip()
        self.conditions = conditions.strip()

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
            row.get("midpointMjdTai"),
            row.get("mjdTai"),
        ]
        for v in candidates:
            if v is None:
                continue
            if isinstance(v, (int, float)):
                fv = float(v)
                # MJD values are typically around 50k-70k.
                if 30_000 <= fv <= 90_000:
                    try:
                        unix = (fv - 40587.0) * 86400.0
                        return datetime.fromtimestamp(unix, tz=timezone.utc)
                    except Exception:
                        continue
                try:
                    return datetime.fromtimestamp(fv, tz=timezone.utc)
                except Exception:
                    continue
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except Exception:
                continue
        return datetime.now(timezone.utc)

    def _build_request(self) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = f"{self.base_url}/query/"
        headers = {"Authorization": f"Token {self.token}", "Content-Type": "application/json"}

        if self.lasair_mode == "lsst":
            selected = self.selected or "diaObjectId, ra, decl"
            tables = self.tables or "objects"
            conditions = self.conditions or "1=1"
            body = {
                "selected": selected,
                "tables": tables,
                "conditions": conditions,
            }
            return url, headers, body

        since = (datetime.now(timezone.utc) - timedelta(days=self.days_back)).isoformat()
        body = {
            "query": self.query,
            "limit": self.limit,
            "since": since,
        }
        return url, headers, body

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self.token}", "Content-Type": "application/json"}

    def fetch_object_detail(self, source_id: str) -> dict[str, Any] | None:
        if not self.token:
            return None

        headers = self._auth_headers()
        sid = quote(str(source_id), safe="")
        candidates = [
            f"{self.base_url}/object/{sid}/",
            f"{self.base_url}/objects/{sid}/",
            f"{self.base_url}/object/{sid}",
            f"{self.base_url}/objects/{sid}",
        ]

        for url in candidates:
            try:
                resp = requests.get(url, headers=headers, timeout=20)
            except requests.RequestException:
                continue
            if resp.status_code in (401, 403):
                LOGGER.warning("Lasair detail auth/permission error for %s", source_id)
                return None
            if resp.status_code == 429:
                LOGGER.warning("Lasair detail rate limited for %s", source_id)
                return None
            if resp.status_code >= 400:
                continue
            try:
                payload = resp.json()
            except ValueError:
                continue
            if isinstance(payload, dict):
                return payload

        # LSST fallback: query endpoint for per-object detail row.
        if self.lasair_mode == "lsst":
            try:
                qurl = f"{self.base_url}/query/"
                body = {
                    "selected": "*",
                    "tables": "objects",
                    "conditions": f"diaObjectId='{source_id}'",
                }
                resp = requests.post(qurl, json=body, headers=headers, timeout=20)
                if resp.status_code < 400:
                    payload = resp.json()
                    if isinstance(payload, list) and payload:
                        return payload[0] if isinstance(payload[0], dict) else {"detail": payload[0]}
                    if isinstance(payload, dict):
                        return payload
            except Exception:
                return None

        return None

    def fetch_events(self) -> list[RawEvent]:
        if not self.token:
            LOGGER.warning("LASAIR_API_TOKEN missing; skipping live Lasair ingestion")
            return []

        url, headers, body = self._build_request()

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
        if len(rows) > self.limit:
            rows = rows[: self.limit]

        events: list[RawEvent] = []
        for row in rows:
            source_id = str(
                row.get("source_id")
                or row.get("objectId")
                or row.get("oid")
                or row.get("diaObjectId")
                or ""
            )
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
