import os
import re
import time
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
        batch_size: int = 25,
        request_delay: float = 2.0,
        max_retries: int = 3,
    ) -> None:
        self.lasair_mode = (lasair_mode or "ztf").strip().lower()
        if self.lasair_mode not in {"ztf", "lsst"}:
            raise ValueError("lasair_mode must be one of: ztf, lsst")

        # Separate token handling for LSST and ZTF
        if self.lasair_mode == "lsst":
            self.token = token or os.getenv("LASAIR_LSST_API_TOKEN", "")
            default_base = "https://lasair.lsst.ac.uk/api"
        else:
            self.token = token or os.getenv("LASAIR_ZTF_API_TOKEN", "")
            default_base = "https://lasair-ztf.lsst.ac.uk/api"

        self.query = query
        self.limit = max(1, min(1000, int(limit)))
        self.days_back = max(1, min(30, int(days_back)))
        env_base_url = os.getenv("LASAIR_API_BASE_URL", "").strip()
        resolved_base = base_url or env_base_url or default_base
        self.base_url = resolved_base.rstrip("/")
        self.selected = selected.strip()
        self.tables = tables.strip()
        self.conditions = conditions.strip()
        self.batch_size = max(1, min(200, int(batch_size)))
        self.request_delay = max(0.0, float(request_delay))
        self.max_retries = max(0, int(max_retries))

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

    def _build_request(self, request_limit: int) -> tuple[str, dict[str, str], dict[str, Any]]:
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
                "limit": request_limit,
            }
            return url, headers, body

        # ZTF currently accepts SQL-style payloads on /query for robust object discovery.
        # Keep legacy query-string mode when explicitly provided with non-default query.
        q = (self.query or "").strip()
        if self.selected and self.tables and self.conditions:
            body = {
                "selected": self.selected,
                "tables": self.tables,
                "conditions": self.conditions,
                "limit": request_limit,
            }
            return url, headers, body

        if q and q != "objectId:*":
            since = (datetime.now(timezone.utc) - timedelta(days=self.days_back)).isoformat()
            body = {
                "query": q,
                "limit": request_limit,
                "since": since,
            }
            return url, headers, body

        body = {
            "selected": "objectId, ramean, decmean, jdgmax",
            "tables": "objects",
            "conditions": "1=1",
            "limit": request_limit,
        }
        return url, headers, body

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self.token}", "Content-Type": "application/json"}

    def _extract_ztf_cutouts_from_object_html(self, source_id: str) -> dict[str, Any] | None:
        """Fallback parser: pull cutout links from object web page HTML for ZTF."""
        page_url = f"https://lasair-ztf.lsst.ac.uk/objects/{quote(str(source_id), safe='')}/"
        try:
            r = requests.get(page_url, timeout=20)
        except requests.RequestException:
            return None
        if r.status_code >= 400:
            return None

        html = r.text
        found: dict[str, str] = {}
        patterns = {
            "science": r"/fits/[^\"'\s>]*_cutoutScience",
            "reference": r"/fits/[^\"'\s>]*_cutoutTemplate",
            "difference": r"/fits/[^\"'\s>]*_cutoutDifference",
        }
        for kind, pat in patterns.items():
            m = re.search(pat, html, flags=re.IGNORECASE)
            if m:
                rel = m.group(0)
                abs_url = f"https://lasair-ztf.lsst.ac.uk{rel}"
                found[kind] = abs_url

        if not found:
            return None

        cutouts = {k: {"url": v} for k, v in found.items()}
        return {
            "objectId": source_id,
            "cutouts": cutouts,
            "_ct_detail_endpoint": page_url,
            "_ct_detail_status": 200,
            "_ct_detail_source": "ztf_object_html",
        }

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
            f"{self.base_url}/object/?objectId={sid}",
            f"{self.base_url}/object/?diaObjectId={sid}",
            f"{self.base_url}/objects/?objectId={sid}",
        ]

        for url in candidates:
            try:
                resp = requests.get(url, headers=headers, timeout=20)
            except requests.RequestException:
                LOGGER.info("Lasair detail request error source=%s endpoint=%s", source_id, url)
                continue

            LOGGER.info(
                "Lasair detail attempt source=%s mode=%s endpoint=%s status=%s",
                source_id,
                self.lasair_mode,
                url,
                resp.status_code,
            )

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
                LOGGER.info("Lasair detail non-JSON source=%s endpoint=%s", source_id, url)
                continue
            if isinstance(payload, dict):
                payload.setdefault("_ct_detail_endpoint", url)
                payload.setdefault("_ct_detail_status", resp.status_code)
                if self.lasair_mode == "ztf":
                    has_cutouts = isinstance(payload.get("cutouts"), dict)
                    if has_cutouts:
                        return payload
                    # Continue to fallback parsing for object-page cutout links.
                    continue
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
                        if isinstance(payload[0], dict):
                            payload[0].setdefault("_ct_detail_endpoint", qurl)
                            return payload[0]
                        return {"detail": payload[0], "_ct_detail_endpoint": qurl}
                    if isinstance(payload, dict):
                        payload.setdefault("_ct_detail_endpoint", qurl)
                        return payload
            except Exception:
                return None

        # ZTF fallback: parse object page cutout links when API detail lacks cutout blocks.
        if self.lasair_mode == "ztf":
            html_detail = self._extract_ztf_cutouts_from_object_html(source_id)
            if html_detail:
                LOGGER.info("Lasair ZTF detail fallback source=%s endpoint=%s status=%s", source_id, html_detail.get("_ct_detail_endpoint"), html_detail.get("_ct_detail_status"))
                return html_detail

        return None

    def _post_with_retries(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> requests.Response | None:
        attempt = 0
        delay = max(1.0, self.request_delay or 1.0)
        while True:
            try:
                resp = requests.post(url, json=body, headers=headers, timeout=30)
            except requests.RequestException as exc:
                LOGGER.error("Lasair request failed: %s", exc)
                return None

            if resp.status_code != 429:
                return resp

            if attempt >= self.max_retries:
                LOGGER.warning("Lasair rate limited (HTTP 429). retries exhausted=%d", self.max_retries)
                return resp

            wait_s = delay * (2**attempt)
            LOGGER.info("Lasair 429 backoff: attempt=%d wait=%.1fs", attempt + 1, wait_s)
            time.sleep(wait_s)
            attempt += 1

    def fetch_events(self) -> list[RawEvent]:
        if not self.token:
            # Clean failure with mode-specific helpful message
            if self.lasair_mode == "lsst":
                LOGGER.error(
                    "Lasair LSST token missing. Set LASAIR_LSST_API_TOKEN environment variable. "
                    "LSST and ZTF use separate tokens."
                )
            else:
                LOGGER.error(
                    "Lasair ZTF token missing. Set LASAIR_ZTF_API_TOKEN environment variable. "
                    "ZTF and LSST use separate tokens."
                )
            return []

        requested_total = self.limit
        batch_size = min(self.batch_size, requested_total)
        LOGGER.info(
            "Lasair batched ingest: total=%d batch_size=%d delay=%.1fs max_retries=%d",
            requested_total,
            batch_size,
            self.request_delay,
            self.max_retries,
        )

        seen_ids: set[str] = set()
        events: list[RawEvent] = []
        batch_index = 0
        target_batches = max(1, (requested_total + batch_size - 1) // batch_size)

        while len(events) < requested_total and batch_index < target_batches:
            remaining = requested_total - len(events)
            request_limit = min(batch_size, remaining)
            url, headers, body = self._build_request(request_limit)
            LOGGER.info(
                "Lasair batch %d/%d: request_limit=%d collected=%d/%d",
                batch_index + 1,
                target_batches,
                request_limit,
                len(events),
                requested_total,
            )

            resp = self._post_with_retries(url, headers, body)
            if resp is None:
                break

            if resp.status_code in (401, 403):
                LOGGER.error("Lasair auth/permission error: HTTP %s", resp.status_code)
                break
            if resp.status_code == 429:
                break
            if resp.status_code >= 400:
                LOGGER.error("Lasair API error HTTP %s: %s", resp.status_code, resp.text[:200])
                break

            try:
                payload = resp.json()
            except ValueError:
                LOGGER.error("Lasair API returned non-JSON payload")
                break

            rows = self._extract_list(payload)
            if not rows:
                break

            new_in_batch = 0
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
                dedupe_key = raw_event_id or source_id
                if dedupe_key in seen_ids:
                    continue
                seen_ids.add(dedupe_key)
                events.append(
                    RawEvent(
                        raw_event_id=raw_event_id,
                        broker_name="lasair_api",
                        source_id=source_id,
                        timestamp=ts,
                        payload=row,
                    )
                )
                new_in_batch += 1
                if len(events) >= requested_total:
                    break

            if new_in_batch == 0:
                LOGGER.info("Lasair batch %d yielded no new rows; stopping early", batch_index + 1)
                break

            batch_index += 1
            if len(events) < requested_total and batch_index < target_batches and self.request_delay > 0:
                time.sleep(self.request_delay)

        LOGGER.info("Fetched %d Lasair raw events", len(events))
        return events
