import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from celestial_triage.models.entities import DetectorScore, NormalizedDetection, RawEvent
from celestial_triage.storage.schema import SCHEMA_SQL


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    def init(self) -> None:
        with self.conn() as c:
            c.executescript(SCHEMA_SQL)
            c.commit()

    def insert_raw_event(self, raw: RawEvent) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO raw_events(raw_event_id, broker_name, source_id, timestamp, payload_json, ingest_time)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    raw.raw_event_id,
                    raw.broker_name,
                    raw.source_id,
                    raw.timestamp.isoformat(),
                    json.dumps(raw.payload),
                    now_iso(),
                ),
            )
            c.commit()

    def insert_detection(self, d: NormalizedDetection) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO detections
                (detection_id, source_id, broker_name, timestamp, ra, dec, magnitude, magnitude_change,
                 moving_flag, class_label, class_confidence, catalog_match_status, raw_payload_reference, ingest_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d.detection_id,
                    d.source_id,
                    d.broker_name,
                    d.timestamp.isoformat(),
                    d.ra,
                    d.dec,
                    d.magnitude,
                    d.magnitude_change,
                    int(d.moving_flag),
                    d.class_label,
                    d.class_confidence,
                    d.catalog_match_status,
                    d.raw_payload_reference,
                    d.ingest_time.isoformat(),
                ),
            )
            c.commit()

    def upsert_candidate_from_source(self, source_id: str) -> str:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM detections WHERE source_id=? ORDER BY timestamp ASC",
                (source_id,),
            ).fetchall()
            if not rows:
                raise ValueError("No detections for source")

            candidate = c.execute(
                "SELECT candidate_id FROM candidates WHERE source_id=?",
                (source_id,),
            ).fetchone()
            candidate_id = candidate["candidate_id"] if candidate else str(uuid.uuid4())

            first_seen = rows[0]["timestamp"]
            last_seen = rows[-1]["timestamp"]
            det_count = len(rows)
            avg_ra = sum(r["ra"] for r in rows) / det_count
            avg_dec = sum(r["dec"] for r in rows) / det_count

            c.execute(
                """
                INSERT OR REPLACE INTO candidates
                (candidate_id, source_id, first_seen, last_seen, detection_count, average_ra, average_dec,
                 current_status, review_status, tags, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT tags FROM candidates WHERE candidate_id=?), ''),
                        COALESCE((SELECT notes FROM candidates WHERE candidate_id=?), ''))
                """,
                (
                    candidate_id,
                    source_id,
                    first_seen,
                    last_seen,
                    det_count,
                    avg_ra,
                    avg_dec,
                    "active",
                    "unreviewed",
                    candidate_id,
                    candidate_id,
                ),
            )

            c.execute("DELETE FROM candidate_detections WHERE candidate_id=?", (candidate_id,))
            for r in rows:
                c.execute(
                    "INSERT OR IGNORE INTO candidate_detections(candidate_id, detection_id) VALUES (?, ?)",
                    (candidate_id, r["detection_id"]),
                )
            c.commit()
            return candidate_id

    def upsert_shared_features(self, candidate_id: str, features: dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO shared_features
                (candidate_id, detection_count, detection_span_hours, avg_magnitude, mag_delta_abs,
                 moving_fraction, poor_catalog_fraction, angular_motion_placeholder, orbit_fit_placeholder,
                 hyperbolic_likelihood_placeholder, anomaly_index_placeholder, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    features.get("detection_count"),
                    features.get("detection_span_hours"),
                    features.get("avg_magnitude"),
                    features.get("mag_delta_abs"),
                    features.get("moving_fraction"),
                    features.get("poor_catalog_fraction"),
                    features.get("angular_motion_placeholder"),
                    features.get("orbit_fit_placeholder"),
                    features.get("hyperbolic_likelihood_placeholder"),
                    features.get("anomaly_index_placeholder"),
                    now_iso(),
                ),
            )
            c.commit()

    def insert_score(self, score: DetectorScore) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT INTO detector_scores(detector_name, candidate_id, score, score_band, reasons_json, version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score.detector_name,
                    score.candidate_id,
                    score.score,
                    score.score_band,
                    json.dumps(score.reasons),
                    score.version,
                    score.created_at.isoformat(),
                ),
            )
            c.commit()

    def upsert_review(self, candidate_id: str, reviewed_flag: bool, tags: str = "", notes: str = "") -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO reviews(candidate_id, reviewed_flag, reviewed_by, reviewed_at, tags, analyst_notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (candidate_id, int(reviewed_flag), "analyst", now_iso() if reviewed_flag else None, tags, notes),
            )
            c.execute(
                "UPDATE candidates SET review_status=?, tags=?, notes=? WHERE candidate_id=?",
                ("reviewed" if reviewed_flag else "unreviewed", tags, notes, candidate_id),
            )
            c.commit()

    def upsert_archive_policy(self, candidate_id: str, tier: str, keep_raw: bool, keep_derived: bool, expiration: str | None, rationale: str) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO archive_policies(candidate_id, retention_tier, keep_raw_payload, keep_derived_products,
                expiration_date, rationale, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (candidate_id, tier, int(keep_raw), int(keep_derived), expiration, rationale, now_iso()),
            )
            c.commit()

    def list_candidate_ids(self) -> list[str]:
        with self.conn() as c:
            rows = c.execute("SELECT candidate_id FROM candidates").fetchall()
        return [r[0] for r in rows]

    def get_candidate_with_features(self, candidate_id: str) -> dict[str, Any]:
        with self.conn() as c:
            cand = c.execute("SELECT * FROM candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
            feat = c.execute("SELECT * FROM shared_features WHERE candidate_id=?", (candidate_id,)).fetchone()
        if not cand:
            raise ValueError("candidate not found")
        out = dict(cand)
        out["features"] = dict(feat) if feat else {}
        return out

    def get_detections_for_candidate(self, candidate_id: str) -> list[dict[str, Any]]:
        with self.conn() as c:
            rows = c.execute(
                """
                SELECT d.* FROM detections d
                JOIN candidate_detections cd ON cd.detection_id=d.detection_id
                WHERE cd.candidate_id=? ORDER BY d.timestamp ASC
                """,
                (candidate_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_scores(self, candidate_id: str) -> list[dict[str, Any]]:
        with self.conn() as c:
            rows = c.execute(
                """
                SELECT ds.* FROM detector_scores ds
                JOIN (
                  SELECT detector_name, MAX(created_at) max_ct
                  FROM detector_scores WHERE candidate_id=? GROUP BY detector_name
                ) latest ON latest.detector_name=ds.detector_name AND latest.max_ct=ds.created_at
                WHERE ds.candidate_id=?
                """,
                (candidate_id, candidate_id),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["reasons"] = json.loads(d["reasons_json"])
            out.append(d)
        return out

    def top_candidates(self, detector_name: str | None = None, score_band: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        filters = []
        vals: list[Any] = []
        if detector_name:
            filters.append("detector_name=?")
            vals.append(detector_name)
        if score_band:
            filters.append("score_band=?")
            vals.append(score_band)

        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        sql = f"""
        SELECT candidate_id, MAX(score) as max_score
        FROM detector_scores
        {where}
        GROUP BY candidate_id
        ORDER BY max_score DESC
        LIMIT ?
        """
        vals.append(limit)

        with self.conn() as c:
            rows = c.execute(sql, vals).fetchall()
        return [dict(r) for r in rows]

    def score_summary(self, candidate_id: str) -> dict[str, Any]:
        with self.conn() as c:
            row = c.execute(
                "SELECT MAX(score) max_score, COUNT(*) n_scores FROM detector_scores WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
        return dict(row) if row else {"max_score": 0.0, "n_scores": 0}
