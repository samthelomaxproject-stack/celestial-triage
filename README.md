# celestial-triage

Layered astronomical candidate detection, anomaly triage, and selective retention.

## Mission
This project ingests Rubin-style/broker alert-like data, normalizes detections into a shared model, runs multiple detector layers over the same candidate objects, ranks interesting candidates for analyst review, and applies retention tiers to avoid uncontrolled data growth.

**Important:** This system does not claim extraordinary identification. It is a triage and prioritization tool.

## Why layered triage
- Ingest once
- Normalize once
- Extract shared features once
- Score many detector domains independently
- Preserve one canonical candidate store (no detector silos)

## Detector classes (v1)
- Unknown satellites / uncatalogued artificial-object candidates
- Near-Earth objects (NEOs)
- Unknown moving objects
- Kuiper Belt object (KBO) candidates
- Interstellar object (ISO) candidates
- Deep-space anomaly candidates

## Architecture overview
- **Ingest**: broker-agnostic adapter interface + mock feed
- **Normalize**: raw alerts → canonical detections
- **Shared features**: computed once per candidate
- **Detectors**: independent weighted rule modules
- **Retention policy**: Tier 1/2/3/4 assignment
- **Storage**: SQLite with compact relational schema
- **UI**: Streamlit analyst dashboard
- **CLI**: pipeline orchestration and testing

## Storage and retention strategy
Retention tiers:
1. **Hot**: active triage, short-lived raw payloads
2. **Warm**: threshold-crossing/interesting reviewed objects
3. **Cold**: archived high-interest compact history
4. **Disposable/Summarized**: low-score, explained events

Policy decisions use detector maxima, detection evidence, review state, poor catalog match, and hyperbolic/anomaly placeholders.

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Quickstart (mock runnable)
```bash
python -m celestial_triage.cli init-db
python -m celestial_triage.cli seed-mock --count 200
python -m celestial_triage.cli run-pipeline
python -m celestial_triage.cli top-candidates --limit 20
python -m celestial_triage.cli launch-ui
```

## CLI commands
```bash
python -m celestial_triage.cli --help
```

## UI
```bash
streamlit run src/celestial_triage/ui/dashboard.py
```

## Current limitations
- Uses mock feed only (no live broker integration yet)
- Orbit fitting/hyperbolic logic are placeholders
- Rule-based scoring only (transparent, non-ML v1)

## Roadmap
- Real Rubin broker adapters
- Better tracklet/orbit features
- PostgreSQL migration path
- Alert subscriptions + collaborative analyst workflows

## Disclaimer
This system ranks unusual astronomical candidates for review. It does **not** assert extraordinary identifications or definitive classifications.
