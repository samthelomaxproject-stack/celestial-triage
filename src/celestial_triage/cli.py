import argparse
import subprocess
from datetime import datetime, timezone

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
from celestial_triage.ingest.mock_feed import MockFeedAdapter
from celestial_triage.ingest.normalizer import normalize_event
from celestial_triage.models.entities import DetectorScore
from celestial_triage.scoring.common import score_band
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


def cmd_seed_mock(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    db.init()
    feed = MockFeedAdapter(count=args.count)
    events = feed.fetch_events()

    for raw in events:
        db.insert_raw_event(raw)
        det = normalize_event(raw)
        db.insert_detection(det)

    source_ids = {e.source_id for e in events}
    for source_id in source_ids:
        db.upsert_candidate_from_source(source_id)

    LOGGER.info("Seeded %d raw events, %d candidate groups", len(events), len(source_ids))


def cmd_extract_features(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    for cid in db.list_candidate_ids():
        dets = db.get_detections_for_candidate(cid)
        feats = extract_shared_features(dets)
        db.upsert_shared_features(cid, feats)
    LOGGER.info("Extracted shared features for %d candidates", len(db.list_candidate_ids()))


def cmd_run_detectors(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    for cid in db.list_candidate_ids():
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
    for cid in db.list_candidate_ids():
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


def cmd_top(args: argparse.Namespace) -> None:
    db = Database(DB_PATH)
    rows = db.top_candidates(detector_name=args.detector, score_band=args.band, limit=args.limit)
    for r in rows:
        print(f"{r['candidate_id']}\t{r['max_score']:.3f}")


def cmd_pipeline(args: argparse.Namespace) -> None:
    cmd_extract_features(args)
    cmd_run_detectors(args)
    cmd_assign_retention(args)


def cmd_launch_ui(args: argparse.Namespace) -> None:
    subprocess.run(["streamlit", "run", "src/celestial_triage/ui/dashboard.py"], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="celestial-triage CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init-db")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("seed-mock")
    p.add_argument("--count", type=int, default=120)
    p.set_defaults(func=cmd_seed_mock)

    p = sub.add_parser("extract-features")
    p.set_defaults(func=cmd_extract_features)

    p = sub.add_parser("run-detectors")
    p.set_defaults(func=cmd_run_detectors)

    p = sub.add_parser("assign-retention")
    p.set_defaults(func=cmd_assign_retention)

    p = sub.add_parser("run-pipeline")
    p.set_defaults(func=cmd_pipeline)

    p = sub.add_parser("top-candidates")
    p.add_argument("--detector", type=str, default=None)
    p.add_argument("--band", type=str, default=None)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_top)

    p = sub.add_parser("launch-ui")
    p.set_defaults(func=cmd_launch_ui)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
