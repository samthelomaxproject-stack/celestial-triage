import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from celestial_triage.config import DB_PATH
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
from celestial_triage.ingest.lasair_api import LasairApiAdapter
from celestial_triage.ingest.mock_feed import MockFeedAdapter
from celestial_triage.ingest.normalizer import normalize_event_safe
from celestial_triage.models.entities import DetectorScore
from celestial_triage.scoring.common import score_band
from celestial_triage.scoring.evaluation import archetype_evaluation_report
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


def _ingest_raw_events(db: Database, events: list, label: str) -> tuple[int, int, int]:
    accepted = 0
    skipped = 0
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

    n_candidates = db.rebuild_candidates_from_detections()
    return accepted, skipped, n_candidates


def cmd_seed_mock(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    db.init()
    feed = MockFeedAdapter(count=args.count)
    events = feed.fetch_events()

    accepted, skipped, n_candidates = _ingest_raw_events(db, events, "mock")

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

    accepted, skipped, n_candidates = _ingest_raw_events(db, events, "external")
    LOGGER.info(
        "Ingested JSONL %s (%d raw, %d accepted, %d skipped), %d candidates total",
        args.input,
        len(events),
        accepted,
        skipped,
        n_candidates,
    )


def cmd_ingest_lasair(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    db.init()

    adapter = LasairApiAdapter(token=args.token, query=args.query, limit=args.limit, days_back=args.days_back)
    events = adapter.fetch_events()
    if not events:
        LOGGER.warning("No ingestible Lasair events returned")
        return

    accepted, skipped, n_candidates = _ingest_raw_events(db, events, "lasair")
    LOGGER.info(
        "Ingested Lasair (%d raw, %d accepted, %d skipped), %d candidates total",
        len(events),
        accepted,
        skipped,
        n_candidates,
    )

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


def _export_rows(rows: list[dict[str, Any]], fmt: str, output: Path) -> None:
    if fmt == "json":
        output.write_text(json.dumps(rows, indent=2))
    elif fmt == "csv":
        with output.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["candidate_id", "max_score"])
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
    else:
        raise ValueError(f"Unsupported export format: {fmt}")


def cmd_top(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    rows = db.top_candidates(detector_name=args.detector, score_band=args.band, limit=args.limit)
    for r in rows:
        print(f"{r['candidate_id']}\t{r['max_score']:.3f}")

    if args.export and args.output:
        _export_rows(rows, args.export, Path(args.output))
        LOGGER.info("Exported %d candidates to %s", len(rows), args.output)


def cmd_pipeline(args: argparse.Namespace) -> None:
    cmd_extract_features(args)
    cmd_run_detectors(args)
    cmd_assign_retention(args)


def cmd_scenario_report(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    report = archetype_evaluation_report(db, top_iso_limit=args.top_iso_limit)
    print(json.dumps(report, indent=2))


def cmd_update_review(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    db.upsert_review(candidate_id=args.candidate_id, review_state=args.state, tags=args.tags, notes=args.notes)
    LOGGER.info("Updated review state for %s -> %s", args.candidate_id, args.state)


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
    p.add_argument("--limit", type=int, default=100, help="Max records to request")
    p.add_argument("--query", type=str, default="objectId:*", help="Lasair query string")
    p.add_argument("--days-back", type=int, default=3, help="Lookback window in days")
    p.add_argument("--token", type=str, default=None, help="Optional Lasair token (or use LASAIR_API_TOKEN env)")
    p.set_defaults(func=cmd_ingest_lasair)

    p = sub.add_parser("extract-features", help="Compute shared candidate features")
    p.set_defaults(func=cmd_extract_features)

    p = sub.add_parser("run-detectors", help="Run all detector scoring layers")
    p.set_defaults(func=cmd_run_detectors)

    p = sub.add_parser("assign-retention", help="Assign retention tiers")
    p.set_defaults(func=cmd_assign_retention)

    p = sub.add_parser("run-pipeline", help="Run extract-features + run-detectors + assign-retention")
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
