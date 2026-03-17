import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from celestial_triage.config import DB_PATH
from celestial_triage.context import build_candidate_context
from celestial_triage.detectors import (
    deep_anomaly_detector,
    iso_detector,
    kbo_detector,
    neo_detector,
    satellite_detector,
    unknown_mover_detector,
)
from celestial_triage.features.extractor import extract_shared_features
from celestial_triage.ingest.external_jsonl import JsonlExternalAdapter
from celestial_triage.ingest.image_assets import extract_image_assets_from_payload
from celestial_triage.ingest.image_preview import render_preview_png
from celestial_triage.ingest.lasair_api import LasairApiAdapter
from celestial_triage.ingest.lasair_presets import PRESETS, resolve_preset
from celestial_triage.ingest.survey_cutouts import ensure_layered_survey_images
from celestial_triage.ingest.mock_feed import MockFeedAdapter
from celestial_triage.ingest.normalizer import normalize_event_safe
from celestial_triage.models.entities import DetectorScore
from celestial_triage.scoring.common import score_band
from celestial_triage.scoring.evaluation import archetype_evaluation_report
from celestial_triage.scoring.followup import build_followup_priority
from celestial_triage.scoring.interpretation import build_interpretation_summary
from celestial_triage.storage.db import Database
from celestial_triage.storage.retention import assign_retention_tier
from celestial_triage.utils.logging import get_logger

LOGGER = get_logger("cli")

DETECTOR_REGISTRY = {
    "satellite_detector": satellite_detector.evaluate,
    "neo_detector": neo_detector.evaluate,
    "unknown_mover_detector": unknown_mover_detector.evaluate,
    "kbo_detector": kbo_detector.evaluate,
    "iso_detector": iso_detector.evaluate,
    "deep_anomaly_detector": deep_anomaly_detector.evaluate,
}


def cmd_init_db(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    db.init()
    LOGGER.info("Initialized DB at %s", DB_PATH)


def _ingest_raw_events(db: Database, events: list, label: str) -> tuple[int, int, int, list[str]]:
    accepted = 0
    skipped = 0
    linked_images = 0
    accepted_source_ids: list[str] = []
    for raw in events:
        db.insert_raw_event(raw)
        det, warnings = normalize_event_safe(raw)
        if det is None:
            skipped += 1
            LOGGER.warning("Skipping %s record %s: %s", label, raw.raw_event_id, ",".join(warnings))
            continue
        if warnings:
            LOGGER.info("%s record %s normalized with warnings: %s", label, raw.raw_event_id, ",".join(warnings))
        db.insert_detection(det)
        accepted += 1
        accepted_source_ids.append(det.source_id)

        image_refs = extract_image_assets_from_payload(raw.payload)
        for item in image_refs:
            embedded = item.get("embedded")
            local_preview = None
            if isinstance(embedded, dict):
                local_preview = render_preview_png(
                    source_id=det.source_id,
                    kind=item["kind"],
                    source_field=item.get("source_field", ""),
                    embedded=embedded,
                )
            db.upsert_image_asset(
                detection_id=det.detection_id,
                source_id=det.source_id,
                broker_name=det.broker_name,
                kind=item["kind"],
                remote_url=item.get("url") or "embedded://local",
                local_path=local_preview,
                source_field=item.get("source_field", ""),
                metadata={**item.get("metadata", {}), "payload_type": (embedded or {}).get("payload_type") if isinstance(embedded, dict) else "url"},
            )
            linked_images += 1

    n_candidates = db.rebuild_candidates_from_detections()
    db.relink_image_assets_to_candidates()
    if linked_images:
        LOGGER.info("Linked %d image assets during %s ingest", linked_images, label)
    return accepted, skipped, n_candidates, sorted(set(accepted_source_ids))


def cmd_seed_mock(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    db.init()
    feed = MockFeedAdapter(count=args.count)
    events = feed.fetch_events()

    accepted, skipped, n_candidates, _ = _ingest_raw_events(db, events, "mock")

    LOGGER.info(
        "Seeded %d raw events (%d accepted, %d skipped), %d candidate groups",
        len(events),
        accepted,
        skipped,
        n_candidates,
    )


def cmd_ingest_jsonl(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    db.init()

    adapter = JsonlExternalAdapter(path=Path(args.input), broker_name=args.broker)
    events = adapter.fetch_events()
    if not events:
        LOGGER.warning("No ingestible events found in %s", args.input)
        return

    accepted, skipped, n_candidates, _ = _ingest_raw_events(db, events, "external")
    LOGGER.info(
        "Ingested JSONL %s (%d raw, %d accepted, %d skipped), %d candidates total",
        args.input,
        len(events),
        accepted,
        skipped,
        n_candidates,
    )


def _fetch_and_link_lasair_cutouts(db: Database, adapter: LasairApiAdapter, source_ids: list[str]) -> dict[str, int]:
    checked = 0
    detail_ok = 0
    detail_fail = 0
    image_assets = 0
    linked_candidates: set[str] = set()

    for source_id in sorted(set(source_ids)):
        checked += 1
        detail = adapter.fetch_object_detail(source_id)
        if not detail:
            detail_fail += 1
            continue
        detail_ok += 1

        image_refs = extract_image_assets_from_payload(detail)
        if not image_refs:
            continue

        det = db.get_latest_detection_for_source(source_id)
        if not det:
            continue

        for item in image_refs:
            embedded = item.get("embedded")
            local_preview = None
            if isinstance(embedded, dict):
                local_preview = render_preview_png(
                    source_id=str(source_id),
                    kind=item["kind"],
                    source_field=item.get("source_field", ""),
                    embedded=embedded,
                )
            db.upsert_image_asset(
                detection_id=det["detection_id"],
                source_id=source_id,
                broker_name=str(det.get("broker_name") or "lasair_api"),
                kind=item["kind"],
                remote_url=item.get("url") or "embedded://local",
                local_path=local_preview,
                source_field=item.get("source_field", ""),
                metadata={
                    "detail_fetch": True,
                    **item.get("metadata", {}),
                    "payload_type": (embedded or {}).get("payload_type") if isinstance(embedded, dict) else "url",
                },
            )
            image_assets += 1

        candidate_id = db.get_candidate_id_for_source(source_id)
        if candidate_id:
            linked_candidates.add(candidate_id)

    db.relink_image_assets_to_candidates()
    return {
        "objects_checked": checked,
        "detail_success": detail_ok,
        "detail_failure": detail_fail,
        "image_assets_discovered": image_assets,
        "linked_candidate_count": len(linked_candidates),
    }


def _link_layered_survey_context_images(db: Database) -> dict[str, int]:
    checked = 0
    pan_ok = 0
    sky_ok = 0
    failures = 0

    for cand in db.list_candidates_brief():
        cid = str(cand["candidate_id"])
        source_id = str(cand["source_id"])
        ra = float(cand.get("average_ra") or 0.0)
        dec = float(cand.get("average_dec") or 0.0)
        if not (-360.0 <= ra <= 360.0 and -90.0 <= dec <= 90.0):
            continue

        checked += 1
        existing = {img.get("kind") for img in db.get_images_for_candidate(cid)}
        det = db.get_latest_detection_for_candidate(cid)
        if not det:
            continue

        out = ensure_layered_survey_images(cid, source_id, ra, dec, existing_kinds={str(k) for k in existing if k})
        if out.get("panstarrs"):
            p = out["panstarrs"]
            db.upsert_image_asset(
                detection_id=det["detection_id"],
                source_id=source_id,
                broker_name="panstarrs",
                kind="survey_context_panstarrs",
                remote_url=str(p["remote_url"]),
                local_path=str(p["local_path"]),
                source_field="survey_context",
                metadata={"service": "panstarrs", "ra": ra, "dec": dec},
            )
            pan_ok += 1
        elif out.get("skyview"):
            s = out["skyview"]
            db.upsert_image_asset(
                detection_id=det["detection_id"],
                source_id=source_id,
                broker_name="skyview",
                kind="survey_context_skyview",
                remote_url=str(s["remote_url"]),
                local_path=str(s["local_path"]),
                source_field="survey_context",
                metadata={"service": "skyview", "ra": ra, "dec": dec},
            )
            sky_ok += 1
        else:
            failures += 1

    db.relink_image_assets_to_candidates()
    return {
        "candidates_checked": checked,
        "panstarrs_context_added": pan_ok,
        "skyview_context_added": sky_ok,
        "context_unavailable": failures,
    }


def cmd_ingest_lasair(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    db.init()

    lasair_mode = (args.lasair_mode or "ztf").strip().lower()
    query = args.query or "objectId:*"
    limit = args.limit if args.limit is not None else 100
    days_back = args.days_back if args.days_back is not None else 3
    selected = (args.selected or "").strip()
    tables = (args.tables or "").strip()
    conditions = (args.conditions or "").strip()

    preset_name = args.preset
    preset = resolve_preset(preset_name)
    if preset:
        query = preset.query if not args.query else args.query
        limit = preset.limit if args.limit is None else args.limit
        days_back = preset.days_back if args.days_back is None else args.days_back
        if lasair_mode == "ztf":
            LOGGER.info(
                "Using Lasair preset '%s' (query=%s, days_back=%d, limit=%d)",
                preset.name,
                query,
                days_back,
                limit,
            )

    if lasair_mode == "lsst" and not (selected and tables and conditions):
        if not selected:
            selected = "diaObjectId, ra, decl"
        if not tables:
            tables = "objects"
        if not conditions:
            conditions = "1=1"
        LOGGER.info(
            "Using LSST Lasair mode (selected=%s, tables=%s, conditions=%s, limit=%d)",
            selected,
            tables,
            conditions,
            limit,
        )

    adapter = LasairApiAdapter(
        token=args.token,
        query=query,
        limit=limit,
        days_back=days_back,
        base_url=args.base_url,
        lasair_mode=lasair_mode,
        selected=selected,
        tables=tables,
        conditions=conditions,
        batch_size=getattr(args, "batch_size", 25),
        request_delay=getattr(args, "request_delay", 2.0),
        max_retries=getattr(args, "max_retries", 3),
    )
    events = adapter.fetch_events()
    if not events:
        LOGGER.warning("No ingestible Lasair events returned")
        return

    accepted, skipped, n_candidates, accepted_source_ids = _ingest_raw_events(db, events, "lasair")

    # Run triage pipeline so summary reflects detector/follow-up state.
    cmd_extract_features(args)
    cmd_run_detectors(args)
    cmd_assign_retention(args)

    cutout_summary: dict[str, int] | None = None
    if args.fetch_cutouts:
        cutout_summary = _fetch_and_link_lasair_cutouts(db, adapter, accepted_source_ids)

    survey_summary: dict[str, int] | None = None
    if not getattr(args, "skip_survey_images", False):
        survey_summary = _link_layered_survey_context_images(db)

    top_scores = db.top_candidates(limit=20)
    detector_hits: dict[str, int] = {}
    priority_hits: dict[str, int] = {}
    for row in top_scores:
        cid = row["candidate_id"]
        score_rows = db.get_latest_scores(cid)
        if score_rows:
            top_det = sorted(score_rows, key=lambda s: float(s["score"]), reverse=True)[0]["detector_name"]
            detector_hits[top_det] = detector_hits.get(top_det, 0) + 1
        cand = db.get_candidate_with_features(cid)
        features = cand.get("features", {})
        score_map = {s["detector_name"]: float(s["score"]) for s in score_rows}
        review_state = str(cand.get("review_status") or "new")
        fp = build_followup_priority(features, score_map, review_state)
        p = fp["priority"]
        priority_hits[p] = priority_hits.get(p, 0) + 1

    LOGGER.info(
        "Ingested Lasair (%d raw, %d accepted, %d skipped), %d candidates total",
        len(events),
        accepted,
        skipped,
        n_candidates,
    )
    LOGGER.info("Top detector categories (sampled): %s", detector_hits)
    LOGGER.info("Top follow-up priorities (sampled): %s", priority_hits)
    if cutout_summary is not None:
        LOGGER.info("Cutout retrieval summary: %s", cutout_summary)
    if survey_summary is not None:
        LOGGER.info("Survey image summary: %s", survey_summary)

def cmd_extract_features(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    candidate_ids = db.list_candidate_ids()
    if not candidate_ids:
        raise RuntimeError("No candidates found. Run `seed-mock` or `ingest-jsonl` first.")

    for cid in candidate_ids:
        dets = db.get_detections_for_candidate(cid)
        feats = extract_shared_features(dets)
        db.upsert_shared_features(cid, feats)
    LOGGER.info("Extracted shared features for %d candidates", len(candidate_ids))


def cmd_run_detectors(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    candidate_ids = db.list_candidate_ids()
    if not candidate_ids:
        raise RuntimeError("No candidates found. Run `seed-mock` or `ingest-jsonl` first.")

    for cid in candidate_ids:
        row = db.get_candidate_with_features(cid)
        feats = row["features"]
        if not feats:
            continue
        for name, fn in DETECTOR_REGISTRY.items():
            score, reasons = fn(feats)
            db.insert_score(
                DetectorScore(
                    detector_name=name,
                    candidate_id=cid,
                    score=score,
                    score_band=score_band(score),
                    reasons=reasons,
                    version="v0.1",
                    created_at=datetime.now(timezone.utc),
                )
            )
    LOGGER.info("Detector scoring complete")


def cmd_assign_retention(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    candidate_ids = db.list_candidate_ids()
    if not candidate_ids:
        raise RuntimeError("No candidates found. Run `seed-mock` or `ingest-jsonl` first.")

    for cid in candidate_ids:
        summary = db.score_summary(cid)
        cand = db.get_candidate_with_features(cid)
        feats = cand.get("features", {})
        tier, keep_raw, keep_derived, expiration, rationale = assign_retention_tier(
            max_score=summary.get("max_score") or 0.0,
            detection_count=int(cand.get("detection_count", 0)),
            reviewed=cand.get("review_status") == "reviewed",
            poor_catalog_fraction=float(feats.get("poor_catalog_fraction", 0.0) or 0.0),
            hyperbolic_hint=float(feats.get("hyperbolic_likelihood_placeholder", 0.0) or 0.0),
            manual_keep=False,
        )
        db.upsert_archive_policy(cid, tier, keep_raw, keep_derived, expiration, rationale)
    LOGGER.info("Retention assignment complete")


def _write_rows(rows: list[dict[str, Any]], fmt: str, output: Path, fieldnames: list[str] | None = None) -> None:
    if fmt == "json":
        output.write_text(json.dumps(rows, indent=2))
    elif fmt == "csv":
        if not fieldnames:
            fieldnames = sorted({k for r in rows for k in r.keys()}) if rows else []
        with output.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
    elif fmt == "md":
        lines = ["# Candidate Export", ""]
        for r in rows:
            lines.append(f"## {r.get('candidate_id','unknown')}")
            lines.append(f"- Review: {r.get('review_state','new')}")
            lines.append(f"- Follow-up: {r.get('followup_priority','low')} ({r.get('followup_score',0)})")
            lines.append(f"- ISO score: {r.get('iso_score',0)}")
            lines.append(f"- Interpretation: {r.get('primary_interpretation','unknown')} ({r.get('interpretation_confidence','weak')})")
            lines.append(f"- Conflict: {r.get('conflict_severity','none')} | Competing: {r.get('competing_interpretations','')}")
            lines.append(f"- Context: {r.get('context_interpretation','')}")
            lines.append(f"- Nearest: {r.get('context_nearest_object','')} | Host hint: {r.get('context_host_hint','')} | Field: {r.get('context_field_density','')}")
            lines.append(f"- Trajectory quality: {r.get('trajectory_quality',0)} (motion={r.get('motion_consistency',0)}, direction={r.get('direction_consistency',0)})")
            lines.append(f"- Retention: {r.get('retention_tier','')}")
            lines.append(f"- Provenance: {r.get('provenance_summary','')}")
            lines.append(f"- Tags: {r.get('tags','')}")
            lines.append(f"- Notes: {r.get('notes','')}")
            lines.append("")
        output.write_text("\n".join(lines))
    else:
        raise ValueError(f"Unsupported export format: {fmt}")


def cmd_top(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    rows = db.top_candidates(detector_name=args.detector, score_band=args.band, limit=args.limit)
    for r in rows:
        print(f"{r['candidate_id']}\t{r['max_score']:.3f}")

    if args.export and args.output:
        _write_rows(rows, args.export, Path(args.output), fieldnames=["candidate_id", "max_score"])
        LOGGER.info("Exported %d candidates to %s", len(rows), args.output)


def cmd_pipeline(args: argparse.Namespace) -> None:
    cmd_extract_features(args)
    cmd_run_detectors(args)
    cmd_assign_retention(args)
    if getattr(args, "fetch_survey_images", False):
        db = Database(DB_PATH)
        summary = _link_layered_survey_context_images(db)
        LOGGER.info("Survey image summary: %s", summary)


def cmd_scenario_report(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    report = archetype_evaluation_report(db, top_iso_limit=args.top_iso_limit)
    print(json.dumps(report, indent=2))


def cmd_update_review(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    db.upsert_review(candidate_id=args.candidate_id, review_state=args.state, tags=args.tags, notes=args.notes)
    LOGGER.info("Updated review state for %s -> %s", args.candidate_id, args.state)


def cmd_followup_report(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    rows = []
    for cid in db.list_candidate_ids():
        cand = db.get_candidate_with_features(cid)
        features = cand.get("features", {})
        scores = db.get_latest_scores(cid)
        score_map = {s["detector_name"]: float(s["score"]) for s in scores}
        review_state = str(cand.get("review_status") or "new")
        f = build_followup_priority(features, score_map, review_state)
        rows.append(
            {
                "candidate_id": cid,
                "priority": f["priority"],
                "priority_score": f["priority_score"],
                "review_state": review_state,
                "iso_score": round(float(score_map.get("iso_detector", 0.0)), 3),
            }
        )
    rows = sorted(rows, key=lambda r: r["priority_score"], reverse=True)[: args.limit]
    print(json.dumps(rows, indent=2))


def build_export_rows(
    db: Database,
    review_state: str | None = None,
    followup_priority: str | None = None,
    detector_presence: str | None = None,
    high_iso_only: bool = False,
    tagged_only: bool = False,
    broker: str | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cid in db.list_candidate_ids():
        cand = db.get_candidate_with_features(cid)
        features = cand.get("features", {})
        scores = db.get_latest_scores(cid)
        score_map = {s["detector_name"]: float(s["score"]) for s in scores}

        state = str(cand.get("review_status") or "new")
        if review_state and state != review_state:
            continue

        tags = str(cand.get("tags") or "")
        if tagged_only and not tags.strip():
            continue

        if detector_presence and detector_presence not in score_map:
            continue

        iso_score = float(score_map.get("iso_detector", 0.0))
        if high_iso_only and iso_score < 0.7:
            continue

        with db.conn() as c:
            det_rows = c.execute(
                """
                SELECT d.broker_name, COUNT(*) as n
                FROM detections d
                JOIN candidate_detections cd ON cd.detection_id=d.detection_id
                WHERE cd.candidate_id=?
                GROUP BY d.broker_name
                """,
                (cid,),
            ).fetchall()
            retention_row = c.execute(
                "SELECT retention_tier FROM archive_policies WHERE candidate_id=?",
                (cid,),
            ).fetchone()

        provenance = {r["broker_name"]: int(r["n"]) for r in det_rows}
        if broker and broker not in provenance:
            continue

        followup = build_followup_priority(features, score_map, state)
        if followup_priority and followup["priority"] != followup_priority:
            continue

        interpretation = build_interpretation_summary(features, score_map)
        context = build_candidate_context(db, cid)

        first_seen = str(cand.get("first_seen") or features.get("first_seen") or "")
        last_seen = str(cand.get("last_seen") or features.get("last_seen") or "")
        detection_count = int(cand.get("detection_count") or features.get("detection_count") or 0)

        row = {
            "candidate_id": cid,
            "review_state": state,
            "tags": tags,
            "notes": str(cand.get("notes") or ""),
            "detector_scores": score_map,
            "iso_score": round(iso_score, 3),
            "followup_priority": followup["priority"],
            "followup_score": followup["priority_score"],
            "followup_reasons": "; ".join(followup["reasons"]),
            "retention_tier": (retention_row["retention_tier"] if retention_row else ""),
            "provenance_summary": ", ".join([f"{k}:{v}" for k, v in provenance.items()]),
            "first_seen": first_seen,
            "last_seen": last_seen,
            "detection_count": detection_count,
            "trajectory_quality": round(float(features.get("trajectory_quality", 0.0) or 0.0), 3),
            "motion_consistency": round(float(features.get("motion_consistency_placeholder", 0.0) or 0.0), 3),
            "direction_consistency": round(float(features.get("direction_consistency_placeholder", 0.0) or 0.0), 3),
            "primary_interpretation": interpretation["primary_interpretation"],
            "interpretation_confidence": interpretation["confidence"],
            "conflict_severity": interpretation["conflict_severity"],
            "competing_interpretations": ", ".join(interpretation["competing_interpretations"]),
            "interpretation_explanation": interpretation["explanation"],
            "context_nearest_object": context.get("nearest_object_summary", ""),
            "context_host_hint": context.get("host_hint", ""),
            "context_nearest_arcsec": context.get("nearest_object_arcsec", ""),
            "context_field_density": context.get("field_density", ""),
            "context_catalog_match": context.get("catalog_match_status", ""),
            "context_interpretation": context.get("context_interpretation", ""),
        }
        out.append(row)
    return out


def cmd_export_candidates(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    rows = build_export_rows(
        db,
        review_state=args.review_state,
        followup_priority=args.followup_priority,
        detector_presence=args.detector,
        high_iso_only=args.high_iso,
        tagged_only=args.tagged_only,
        broker=args.broker,
    )

    output = Path(args.output)
    if args.format == "csv":
        csv_rows = []
        for r in rows:
            flat = dict(r)
            flat["detector_scores"] = json.dumps(flat["detector_scores"])
            csv_rows.append(flat)
        _write_rows(
            csv_rows,
            "csv",
            output,
            fieldnames=[
                "candidate_id",
                "review_state",
                "tags",
                "notes",
                "iso_score",
                "followup_priority",
                "followup_score",
                "followup_reasons",
                "retention_tier",
                "provenance_summary",
                "first_seen",
                "last_seen",
                "detection_count",
                "trajectory_quality",
                "motion_consistency",
                "direction_consistency",
                "primary_interpretation",
                "interpretation_confidence",
                "conflict_severity",
                "competing_interpretations",
                "interpretation_explanation",
                "context_nearest_object",
                "context_host_hint",
                "context_nearest_arcsec",
                "context_field_density",
                "context_catalog_match",
                "context_interpretation",
                "detector_scores",
            ],
        )
    else:
        _write_rows(rows, args.format, output)

    LOGGER.info("Exported %d candidates to %s (%s)", len(rows), output, args.format)


def _bundle_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    detector_dist: dict[str, int] = {}
    followup_dist: dict[str, int] = {}
    interp_dist: dict[str, int] = {}
    provenance_dist: dict[str, int] = {}

    for r in rows:
        det_scores = r.get("detector_scores", {})
        if isinstance(det_scores, dict) and det_scores:
            top = sorted(det_scores.items(), key=lambda kv: kv[1], reverse=True)[0][0]
            detector_dist[top] = detector_dist.get(top, 0) + 1

        fp = str(r.get("followup_priority") or "low")
        followup_dist[fp] = followup_dist.get(fp, 0) + 1

        pi = str(r.get("primary_interpretation") or "unknown")
        interp_dist[pi] = interp_dist.get(pi, 0) + 1

        for token in str(r.get("provenance_summary") or "").split(","):
            token = token.strip()
            if not token:
                continue
            k = token.split(":")[0].strip()
            provenance_dist[k] = provenance_dist.get(k, 0) + 1

    return {
        "candidate_count": len(rows),
        "detector_distribution": detector_dist,
        "followup_priority_distribution": followup_dist,
        "interpretation_distribution": interp_dist,
        "provenance_distribution": provenance_dist,
    }


def cmd_bundle_cases(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    rows = build_export_rows(
        db,
        review_state=args.review_state,
        followup_priority=args.followup_priority,
        detector_presence=args.detector,
        high_iso_only=args.high_iso,
        tagged_only=args.tagged_only,
        broker=args.broker,
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = _bundle_summary(rows)
    summary_json_path = out_dir / "summary.json"
    summary_md_path = out_dir / "summary.md"

    summary_json_path.write_text(json.dumps({"summary": summary, "items": rows}, indent=2))

    md_lines = [
        "# Analyst Case Bundle",
        "",
        f"Candidates included: **{summary['candidate_count']}**",
        "",
        "## Detector distribution",
        json.dumps(summary["detector_distribution"], indent=2),
        "",
        "## Follow-up priority distribution",
        json.dumps(summary["followup_priority_distribution"], indent=2),
        "",
        "## Interpretation distribution",
        json.dumps(summary["interpretation_distribution"], indent=2),
        "",
        "## Provenance summary",
        json.dumps(summary["provenance_distribution"], indent=2),
    ]
    summary_md_path.write_text("\n".join(md_lines))

    if args.include_details:
        details_dir = out_dir / "candidates"
        details_dir.mkdir(exist_ok=True)
        for r in rows:
            cid = str(r.get("candidate_id") or "unknown")
            (details_dir / f"{cid}.json").write_text(json.dumps(r, indent=2))

    LOGGER.info(
        "Bundle created at %s (candidates=%d, details=%s)",
        out_dir,
        len(rows),
        args.include_details,
    )


def cmd_launch_ui(args: argparse.Namespace) -> None:
    subprocess.run(["streamlit", "run", "src/celestial_triage/ui/dashboard.py"], check=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="celestial-triage CLI (mock-enabled astronomical candidate triage)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init-db", help="Initialize SQLite schema")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("seed-mock", help="Seed mock broker events and normalized detections")
    p.add_argument("--count", type=int, default=120, help="Number of mock events to generate")
    p.set_defaults(func=cmd_seed_mock)

    p = sub.add_parser("ingest-jsonl", help="Ingest external JSONL records into canonical detections")
    p.add_argument("--input", required=True, help="Path to JSONL input file")
    p.add_argument("--broker", default="external_jsonl", help="Broker/source name label")
    p.set_defaults(func=cmd_ingest_jsonl)

    p = sub.add_parser("ingest-lasair", help="Ingest live Lasair API records")
    p.add_argument("--preset", choices=sorted(PRESETS.keys()), default=None, help="Optional query preset")
    p.add_argument("--lasair-mode", choices=["ztf", "lsst"], default="ztf", help="Lasair broker request mode")
    p.add_argument("--base-url", type=str, default=None, help="Lasair API base URL (or use LASAIR_API_BASE_URL env)")
    p.add_argument("--limit", type=int, default=None, help="Total records requested across batched broker calls")
    p.add_argument("--batch-size", type=int, default=25, help="Records requested per broker call")
    p.add_argument("--request-delay", type=float, default=2.0, help="Delay seconds between broker calls")
    p.add_argument("--max-retries", type=int, default=3, help="Max retries on HTTP 429 with exponential backoff")
    p.add_argument("--query", type=str, default="", help="Lasair query string for ztf mode (overrides preset query)")
    p.add_argument("--days-back", type=int, default=None, help="Lookback window in days for ztf mode")
    p.add_argument("--selected", type=str, default="", help="LSST mode SELECT list")
    p.add_argument("--tables", type=str, default="", help="LSST mode FROM tables")
    p.add_argument("--conditions", type=str, default="", help="LSST mode WHERE conditions")
    p.add_argument("--fetch-cutouts", action="store_true", help="Fetch object detail/cutout references after ingest")
    p.add_argument("--skip-survey-images", action="store_true", help="Skip layered Pan-STARRS/SkyView survey context retrieval")
    p.add_argument("--token", type=str, default=None, help="Optional Lasair token (or use LASAIR_API_TOKEN env)")
    p.set_defaults(func=cmd_ingest_lasair)

    p = sub.add_parser("extract-features", help="Compute shared candidate features")
    p.set_defaults(func=cmd_extract_features)

    p = sub.add_parser("run-detectors", help="Run all detector scoring layers")
    p.set_defaults(func=cmd_run_detectors)

    p = sub.add_parser("assign-retention", help="Assign retention tiers")
    p.set_defaults(func=cmd_assign_retention)

    p = sub.add_parser("run-pipeline", help="Run extract-features + run-detectors + assign-retention")
    p.add_argument("--fetch-survey-images", action="store_true", help="Also fetch layered survey context images")
    p.set_defaults(func=cmd_pipeline)

    p = sub.add_parser("top-candidates", help="List top ranked candidates")
    p.add_argument("--detector", type=str, default=None, help="Filter by detector name")
    p.add_argument("--band", type=str, default=None, help="Filter by score band")
    p.add_argument("--limit", type=int, default=20, help="Max rows to list")
    p.add_argument("--export", choices=["csv", "json"], default=None, help="Optional export format")
    p.add_argument("--output", type=str, default=None, help="Export file path")
    p.set_defaults(func=cmd_top)

    p = sub.add_parser("scenario-report", help="Summarize mock archetype vs detector outcomes")
    p.add_argument("--top-iso-limit", type=int, default=10, help="Number of top ISO candidates to include")
    p.set_defaults(func=cmd_scenario_report)

    p = sub.add_parser("update-review", help="Update candidate analyst review state/notes")
    p.add_argument("--candidate-id", required=True, help="Candidate id")
    p.add_argument("--state", choices=["new", "reviewing", "follow-up", "dismissed"], required=True)
    p.add_argument("--tags", default="", help="Comma-separated tags")
    p.add_argument("--notes", default="", help="Analyst notes")
    p.set_defaults(func=cmd_update_review)

    p = sub.add_parser("followup-report", help="List candidates by follow-up priority")
    p.add_argument("--limit", type=int, default=20, help="Max rows")
    p.set_defaults(func=cmd_followup_report)

    p = sub.add_parser("export-candidates", help="Export reviewed/triage candidate handoff data")
    p.add_argument("--format", choices=["json", "csv", "md"], required=True)
    p.add_argument("--output", required=True, help="Output file path")
    p.add_argument("--review-state", choices=["new", "reviewing", "follow-up", "dismissed"], default=None)
    p.add_argument("--followup-priority", choices=["low", "medium", "high", "urgent"], default=None)
    p.add_argument("--detector", default=None, help="Require detector presence (e.g. iso_detector)")
    p.add_argument("--high-iso", action="store_true", help="Only include ISO score >= 0.7")
    p.add_argument("--tagged-only", action="store_true", help="Only include candidates with tags")
    p.add_argument("--broker", default=None, help="Only include candidates seen from this broker/source")
    p.set_defaults(func=cmd_export_candidates)

    p = sub.add_parser("bundle-cases", help="Create analyst case bundle directory")
    p.add_argument("--output-dir", required=True, help="Bundle output directory")
    p.add_argument("--review-state", choices=["new", "reviewing", "follow-up", "dismissed"], default=None)
    p.add_argument("--followup-priority", choices=["low", "medium", "high", "urgent"], default=None)
    p.add_argument("--detector", default=None, help="Require detector presence")
    p.add_argument("--high-iso", action="store_true", help="Only include ISO score >= 0.7")
    p.add_argument("--tagged-only", action="store_true", help="Only include tagged candidates")
    p.add_argument("--broker", default=None, help="Only include candidates with this provenance source")
    p.add_argument("--include-details", action="store_true", help="Write per-candidate detail JSON files")
    p.set_defaults(func=cmd_bundle_cases)

    p = sub.add_parser("launch-ui", help="Launch Streamlit dashboard")
    p.set_defaults(func=cmd_launch_ui)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if getattr(args, "export", None) and not getattr(args, "output", None):
            parser.error("--output is required when using --export")
        args.func(args)
    except Exception as exc:  # pragma: no cover
        LOGGER.error("Command failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
