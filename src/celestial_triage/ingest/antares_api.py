from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

from celestial_triage.ingest.base import BrokerAdapter
from celestial_triage.models.entities import RawEvent
from celestial_triage.utils.logging import get_logger

LOGGER = get_logger("antares_api")


class AntaresApiAdapter(BrokerAdapter):
    """ANTARES broker adapter (NOIRLab JSON:API).

    Fetches loci from ANTARES API and maps them into RawEvent records for the
    shared normalizer/candidate pipeline.
    """

    def __init__(
        self,
        api_url: str | None = None,
        token: str | None = None,
        limit: int = 100,
        offset: int = 0,
        timeout: float = 30.0,
    ) -> None:
        self.api_url = (api_url or os.getenv("ANTARES_API_URL") or "https://api.antares.noirlab.edu/v1").rstrip("/")
        self.token = token or os.getenv("ANTARES_API_TOKEN", "")
        self.limit = max(1, min(1000, int(limit)))
        self.offset = max(0, int(offset))
        self.timeout = max(5.0, float(timeout))

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @staticmethod
    def _iso_from_mjd(mjd: Any) -> datetime:
        try:
            fv = float(mjd)
            unix = (fv - 40587.0) * 86400.0
            return datetime.fromtimestamp(unix, tz=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    def _extract_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = payload.get("data")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
        return []

    def _request_payload(self, url: str, params: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str | None]:
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            LOGGER.error("ANTARES request failed: %s", exc)
            return None, None

        if resp.status_code in (401, 403):
            LOGGER.error("ANTARES auth/permission error: HTTP %s", resp.status_code)
            return None, None

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            try:
                wait_s = max(1.0, float(retry_after)) if retry_after else 3.0
            except Exception:
                wait_s = 3.0
            LOGGER.warning("ANTARES rate-limited (429), waiting %.1fs", wait_s)
            time.sleep(wait_s)
            return None, None

        if resp.status_code >= 400:
            LOGGER.error("ANTARES API error HTTP %s: %s", resp.status_code, resp.text[:200])
            return None, None

        try:
            payload = resp.json()
        except ValueError:
            LOGGER.error("ANTARES API returned non-JSON payload")
            return None, None

        links = payload.get("links") if isinstance(payload, dict) else {}
        next_url = links.get("next") if isinstance(links, dict) else None
        return payload, (str(next_url) if next_url else None)

    def fetch_events(self) -> list[RawEvent]:
        url = f"{self.api_url}/loci"
        params: dict[str, Any] | None = {
            "page[size]": self.limit,
            "page[offset]": self.offset,
        }

        events: list[RawEvent] = []
        seen_event_ids: set[str] = set()
        page_count = 0
        max_pages = 5000

        while len(events) < self.limit and url and page_count < max_pages:
            page_count += 1
            payload, next_url = self._request_payload(url, params=params)
            # After first request, follow links.next directly.
            params = None
            if payload is None:
                break

            rows = self._extract_rows(payload)
            if not rows:
                break

            for row in rows:
                if len(events) >= self.limit:
                    break

                attrs = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
                props = attrs.get("properties") if isinstance(attrs.get("properties"), dict) else {}

                source_id = str(row.get("id") or "").strip()
                if not source_id:
                    LOGGER.warning("Skipping ANTARES row without locus id")
                    continue

                ra = attrs.get("ra")
                dec = attrs.get("dec")
                newest_mjd = props.get("newest_alert_observation_time")
                ts = self._iso_from_mjd(newest_mjd)

                raw_event_id = str(props.get("newest_alert_id") or f"{source_id}:{ts.isoformat()}")
                if raw_event_id in seen_event_ids:
                    continue
                seen_event_ids.add(raw_event_id)

                normalized_payload: dict[str, Any] = {
                    "source_id": source_id,
                    "ra": ra,
                    "dec": dec,
                    "magnitude": props.get("newest_alert_magnitude", props.get("brightest_alert_magnitude")),
                    "timestamp": ts.isoformat(),
                    "catalog_match_status": "unknown",
                    "class_label": props.get("anomaly_type") or attrs.get("tags") or "unknown",
                    "class_confidence": props.get("anomaly_score") if "anomaly_score" in props else 0.0,
                    "survey": props.get("survey") or "antares",
                    "antares_locus_id": source_id,
                    "antares_newest_alert_id": props.get("newest_alert_id"),
                    "antares_num_alerts": props.get("num_alerts"),
                    "antares_properties": props,
                }

                events.append(
                    RawEvent(
                        raw_event_id=raw_event_id,
                        broker_name="antares_api",
                        source_id=source_id,
                        timestamp=ts,
                        payload=normalized_payload,
                    )
                )

            if len(events) >= self.limit:
                break

            url = next_url or ""

        LOGGER.info("Fetched %d ANTARES raw events across %d page(s)", len(events), page_count)
        return events
