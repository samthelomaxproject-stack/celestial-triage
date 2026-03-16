#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[smoke] removing old db"
rm -f celestial_triage.db

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[smoke] init db"
"$PYTHON_BIN" -m celestial_triage.cli init-db

echo "[smoke] seed mock"
"$PYTHON_BIN" -m celestial_triage.cli seed-mock --count 120

echo "[smoke] run pipeline"
"$PYTHON_BIN" -m celestial_triage.cli run-pipeline

echo "[smoke] top candidates"
"$PYTHON_BIN" -m celestial_triage.cli top-candidates --limit 10

echo "[smoke] done"
