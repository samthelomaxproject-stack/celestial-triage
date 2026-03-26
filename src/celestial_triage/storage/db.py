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
            # Lightweight migration for older DBs missing newer shared_features columns
            existing_cols = {
                r[1]
                for r in c.execute("PRAGMA table_info(shared_features)").fetchall()
            }
            required_cols = {
                "first_seen": "TEXT",
                "last_seen": "TEXT",
                "brightness_trend": "REAL",
                "motion_rate_deg_per_hour": "REAL",
                "motion_consistency_placeholder": "REAL",
                "direction_consistency_placeholder": "REAL",
                "heading_deg_placeholder": "REAL",
                "heading_change_consistency": "REAL",
                "path_smoothness_placeholder": "REAL",
                "trajectory_quality": "REAL",
                "avg_class_confidence": "REAL",
                "orbit_fit_quality": "REAL",
                "eccentricity_placeholder": "REAL",
                "hyperbolic_likelihood": "REAL",
                "inbound_outbound_placeholder": "TEXT",
            }
            for col, col_type in required_cols.items():
                if col not in existing_cols:
                    c.execute(f"ALTER TABLE shared_features ADD COLUMN {col} {col_type}")

            det_cols = {r[1] for r in c.execute("PRAGMA table_info(detections)").fetchall()}
            if "mock_archetype_label" not in det_cols:
                c.execute("ALTER TABLE detections ADD COLUMN mock_archetype_label TEXT")

            cand_cols = {r[1] for r in c.execute("PRAGMA table_info(candidates)").fetchall()}
            if "mock_archetype_label" not in cand_cols:
                c.execute("ALTER TABLE candidates ADD COLUMN mock_archetype_label TEXT")

            review_cols = {r[1] for r in c.execute("PRAGMA table_info(reviews)").fetchall()}
            if "review_state" not in review_cols:
                c.execute("ALTER TABLE reviews ADD COLUMN review_state TEXT")

            # image_assets table migration support for existing DBs.
            image_cols = {r[1] for r in c.execute("PRAGMA table_info(image_assets)").fetchall()}
            if image_cols:
                required_image_cols = {
                    "detection_id": "TEXT",
                    "candidate_id": "TEXT",
                    "source_id": "TEXT",
                    "kind": "TEXT",
                    "broker_name": "TEXT",
                    "source_field": "TEXT",
                    "remote_url": "TEXT",
                    "local_path": "TEXT",
                    "fetch_status": "TEXT",
                    "error_message": "TEXT",
                    "metadata_json": "TEXT",
                    "created_at": "TEXT",
                    "updated_at": "TEXT",
                }
                for col, col_type in required_image_cols.items():
                    if col not in image_cols:
                        c.execute(f"ALTER TABLE image_assets ADD COLUMN {col} {col_type}")
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
                 moving_flag, class_label, class_confidence, catalog_match_status, raw_payload_reference, ingest_time,
                 mock_archetype_label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    d.mock_archetype_label,
                ),
            )
            c.commit()

    def upsert_image_asset(
        self,
        detection_id: str,
        source_id: str,
        broker_name: str,
        kind: str,
        remote_url: str,
        source_field: str = "",
        metadata: dict[str, Any] | None = None,
        fetch_status: str = "linked",
        local_path: str | None = None,
        error_message: str | None = None,
    ) -> None:
        image_id = str(uuid.uuid4())
        with self.conn() as c:
            row = c.execute(
                "SELECT image_id FROM image_assets WHERE detection_id=? AND kind=? AND remote_url=?",
                (detection_id, kind, remote_url),
            ).fetchone()
            if row:
                image_id = row["image_id"]
            c.execute(
                """
                INSERT OR REPLACE INTO image_assets
                (image_id, detection_id, candidate_id, source_id, kind, broker_name, source_field,
                 remote_url, local_path, fetch_status, error_message, metadata_json, created_at, updated_at)
                VALUES
                (?, ?, COALESCE((SELECT candidate_id FROM image_assets WHERE image_id=?), NULL), ?, ?, ?, ?, ?, ?, ?, ?, ?,
                 COALESCE((SELECT created_at FROM image_assets WHERE image_id=?), ?), ?)
                """,
                (
                    image_id,
                    detection_id,
                    image_id,
                    source_id,
                    kind,
                    broker_name,
                    source_field,
                    remote_url,
                    local_path,
                    fetch_status,
                    error_message,
                    json.dumps(metadata or {}),
                    image_id,
                    now_iso(),
                    now_iso(),
                ),
            )
            c.commit()

    def relink_image_assets_to_candidates(self) -> None:
        with self.conn() as c:
            c.execute(
                """
                UPDATE image_assets
                SET candidate_id = (
                    SELECT cd.candidate_id
                    FROM candidate_detections cd
                    WHERE cd.detection_id = image_assets.detection_id
                    LIMIT 1
                ),
                updated_at = ?
                WHERE detection_id IS NOT NULL
                """,
                (now_iso(),),
            )
            c.commit()

    def get_images_for_candidate(self, candidate_id: str) -> list[dict[str, Any]]:
        with self.conn() as c:
            rows = c.execute(
                """
                SELECT * FROM image_assets
                WHERE candidate_id=?
                ORDER BY CASE kind
                    WHEN 'science' THEN 1
                    WHEN 'reference' THEN 2
                    WHEN 'difference' THEN 3
                    WHEN 'survey_context_panstarrs' THEN 4
                    WHEN 'survey_context_skyview' THEN 5
                    ELSE 9 END,
                         created_at DESC
                """,
                (candidate_id,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["metadata"] = json.loads(d.get("metadata_json") or "{}")
            except Exception:
                d["metadata"] = {}
            out.append(d)
        return out

    def rebuild_candidates_from_detections(self) -> int:
        """Rebuild/refresh candidate summaries and linkage from all detections."""
        with self.conn() as c:
            source_ids = [r[0] for r in c.execute("SELECT DISTINCT source_id FROM detections").fetchall()]
        for source_id in source_ids:
            self.upsert_candidate_from_source(source_id)
        return len(source_ids)

    def _coherent_detection_subset(self, rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
        """Select a coherent trajectory subset to reduce misleading rollups.

        Heuristic: keep detections with plausible incremental steps and heading changes.
        """
        if len(rows) <= 2:
            return rows

        def _heading(a: sqlite3.Row, b: sqlite3.Row) -> float:
            import math

            d_ra = float(b["ra"]) - float(a["ra"])
            d_dec = float(b["dec"]) - float(a["dec"])
            return (math.degrees(math.atan2(d_ra, d_dec)) + 360.0) % 360.0

        def _step(a: sqlite3.Row, b: sqlite3.Row) -> float:
            import math

            return math.sqrt((float(b["ra"]) - float(a["ra"])) ** 2 + (float(b["dec"]) - float(a["dec"])) ** 2)

        accepted: list[sqlite3.Row] = [rows[0], rows[1]]
        prev_heading = _heading(rows[0], rows[1])
        prev_step = max(_step(rows[0], rows[1]), 1e-6)

        for r in rows[2:]:
            h = _heading(accepted[-1], r)
            step = _step(accepted[-1], r)
            heading_delta = abs(h - prev_heading)
            heading_delta = min(heading_delta, 360.0 - heading_delta)

            step_ratio = step / max(prev_step, 1e-6)
            plausible = (heading_delta <= 75.0) and (0.2 <= step_ratio <= 4.5)

            if plausible:
                accepted.append(r)
                prev_heading = h
                prev_step = max(step, 1e-6)

        # If filtering was too aggressive, keep original to avoid data loss.
        if len(accepted) < max(2, int(0.5 * len(rows))):
            return rows
        return accepted

    def upsert_candidate_from_source(self, source_id: str) -> str:
        with self.conn() as c:
            all_rows = c.execute(
                "SELECT * FROM detections WHERE source_id=? ORDER BY timestamp ASC",
                (source_id,),
            ).fetchall()
            if not all_rows:
                raise ValueError("No detections for source")

            rows = self._coherent_detection_subset(all_rows)

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

            # Use dominant archetype label for demo/testing visibility.
            labels = [str(r["mock_archetype_label"] or "") for r in rows if r["mock_archetype_label"]]
            archetype = max(set(labels), key=labels.count) if labels else ""

            c.execute(
                """
                INSERT OR REPLACE INTO candidates
                (candidate_id, source_id, first_seen, last_seen, detection_count, average_ra, average_dec,
                 current_status, review_status, mock_archetype_label, tags, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT tags FROM candidates WHERE candidate_id=?), ''),
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
                    "new",
                    archetype,
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
                (candidate_id, detection_count, first_seen, last_seen, detection_span_hours, avg_magnitude, mag_delta_abs,
                 brightness_trend, moving_fraction, motion_rate_deg_per_hour, motion_consistency_placeholder,
                 direction_consistency_placeholder, heading_deg_placeholder, heading_change_consistency,
                 path_smoothness_placeholder, trajectory_quality, poor_catalog_fraction,
                 avg_class_confidence, angular_motion_placeholder, orbit_fit_quality, eccentricity_placeholder,
                 hyperbolic_likelihood, inbound_outbound_placeholder, orbit_fit_placeholder,
                 hyperbolic_likelihood_placeholder, anomaly_index_placeholder, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    features.get("detection_count"),
                    features.get("first_seen"),
                    features.get("last_seen"),
                    features.get("detection_span_hours"),
                    features.get("avg_magnitude"),
                    features.get("mag_delta_abs"),
                    features.get("brightness_trend"),
                    features.get("moving_fraction"),
                    features.get("motion_rate_deg_per_hour"),
                    features.get("motion_consistency_placeholder"),
                    features.get("direction_consistency_placeholder"),
                    features.get("heading_deg_placeholder"),
                    features.get("heading_change_consistency"),
                    features.get("path_smoothness_placeholder"),
                    features.get("trajectory_quality"),
                    features.get("poor_catalog_fraction"),
                    features.get("avg_class_confidence"),
                    features.get("angular_motion_placeholder"),
                    features.get("orbit_fit_quality"),
                    features.get("eccentricity_placeholder"),
                    features.get("hyperbolic_likelihood"),
                    features.get("inbound_outbound_placeholder"),
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

    def upsert_review(self, candidate_id: str, review_state: str, tags: str = "", notes: str = "") -> None:
        valid_states = {"new", "reviewing", "follow-up", "dismissed"}
        state = review_state if review_state in valid_states else "new"
        reviewed_flag = state in {"reviewing", "follow-up", "dismissed"}
        with self.conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO reviews(candidate_id, reviewed_flag, review_state, reviewed_by, reviewed_at, tags, analyst_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (candidate_id, int(reviewed_flag), state, "analyst", now_iso() if reviewed_flag else None, tags, notes),
            )
            c.execute(
                "UPDATE candidates SET review_status=?, tags=?, notes=? WHERE candidate_id=?",
                (state, tags, notes, candidate_id),
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

    def list_candidates_brief(self) -> list[dict[str, Any]]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT candidate_id, source_id, average_ra, average_dec FROM candidates"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_candidate_id_for_source(self, source_id: str) -> str | None:
        with self.conn() as c:
            row = c.execute("SELECT candidate_id FROM candidates WHERE source_id=?", (source_id,)).fetchone()
        return str(row[0]) if row else None

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

    def get_latest_detection_for_source(self, source_id: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT * FROM detections WHERE source_id=? ORDER BY timestamp DESC LIMIT 1",
                (source_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_latest_detection_for_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute(
                """
                SELECT d.*
                FROM detections d
                JOIN candidate_detections cd ON cd.detection_id=d.detection_id
                WHERE cd.candidate_id=?
                ORDER BY d.timestamp DESC
                LIMIT 1
                """,
                (candidate_id,),
            ).fetchone()
        return dict(row) if row else None

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
    
    def insert_plate_solve(
        self,
        solve_id: str,
        image_path: str,
        status: str,
        ra_center: float | None,
        dec_center: float | None,
        field_width_deg: float | None,
        field_height_deg: float | None,
        orientation_deg: float | None,
        pixel_scale_arcsec: float | None,
        backend: str,
        job_id: str | None,
        error_message: str | None,
        metadata_json: str | None,
        candidate_id: str | None = None,
    ) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT INTO plate_solves (
                    solve_id, image_path, status, ra_center, dec_center,
                    field_width_deg, field_height_deg, orientation_deg, pixel_scale_arcsec,
                    backend, job_id, error_message, metadata_json, solved_at, candidate_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    solve_id, image_path, status, ra_center, dec_center,
                    field_width_deg, field_height_deg, orientation_deg, pixel_scale_arcsec,
                    backend, job_id, error_message, metadata_json, now_iso(), candidate_id
                )
            )
            c.commit()
    
    def get_plate_solve(self, solve_id: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT * FROM plate_solves WHERE solve_id = ?",
                (solve_id,)
            ).fetchone()
        return dict(row) if row else None
    
    def find_nearby_candidates(self, ra: float, dec: float, radius_deg: float = 0.01) -> list[dict[str, Any]]:
        """Find candidates near given coordinates (simple box search)."""
        with self.conn() as c:
            rows = c.execute(
                """
                SELECT candidate_id, source_id, average_ra, average_dec
                FROM candidates
                WHERE average_ra BETWEEN ? AND ?
                  AND average_dec BETWEEN ? AND ?
                """,
                (ra - radius_deg, ra + radius_deg, dec - radius_deg, dec + radius_deg)
            ).fetchall()
        return [dict(r) for r in rows]
    
    def link_plate_solve_to_candidate(self, solve_id: str, candidate_id: str) -> None:
        """Associate a plate solve with an existing candidate."""
        with self.conn() as c:
            c.execute(
                "UPDATE plate_solves SET candidate_id = ? WHERE solve_id = ?",
                (candidate_id, solve_id)
            )
            c.commit()
