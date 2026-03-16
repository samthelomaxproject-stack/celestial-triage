# celestial-triage

Layered astronomical candidate detection, anomaly triage, and selective retention.

## Mission
This project ingests Rubin-style/broker alert-like data, normalizes detections into a shared model, runs multiple detector layers over the same candidate objects, ranks interesting candidates for analyst review, and applies retention tiers to avoid uncontrolled data growth.

**Important:** This system does not claim extraordinary identification. It is a triage and prioritization tool.

## What currently works (validated)
- Mock broker ingestion
- Normalization into canonical detections
- Candidate grouping/track building and shared feature extraction
- Motion analysis upgrades (motion rate, consistency, heading/direction placeholders)
- Orbit-fit scaffolding (orbit_fit_quality, eccentricity_placeholder, hyperbolic_likelihood, inbound/outbound placeholder)
- Scenario realism with explicit mock archetypes (inbound/outbound ISO-like, KBO-like, NEO-like, satellite-like, anomaly-like)
- Scenario evaluation helper for detector/archetype alignment insights
- Six detector modules with transparent scoring + reasons using candidate-level aggregates (span, trend, motion, orbit placeholders)
- Score persistence in SQLite
- Retention tier assignment (`hot`, `warm`, `cold`, `disposable`)
- Streamlit triage dashboard
- CLI workflow + export of top candidates (`csv` / `json`)
- One-command smoke test script

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
  - required normalized field contract is documented in `ingest/base.py` (`REQUIRED_NORMALIZED_FIELDS`)
- **External-readiness**: includes a narrow isolated `JsonlExternalAdapter` scaffold for first real-source integration prep

### JSONL input notes (external path)
Preferred keys:
- `source_id` (or fallback `objectId`)
- `timestamp` (ISO8601 preferred)
- `ra`/`dec` (or `ra_deg`/`dec_deg`)
- optional brightness/motion/class fields (`mag`, `magpsf`, `moving`, `is_moving`, `class_label`, `confidence`, etc.)

Records missing usable coordinates are skipped because they cannot be mapped into a normalized detection.

Sample files under `sample_data/` are **demo records** for schema/ingestion validation unless otherwise noted.
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

## Setup / install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Initialize DB
```bash
python -m celestial_triage.cli init-db
```

## Seed mock data
```bash
python -m celestial_triage.cli seed-mock --count 200
```

## Ingest external JSONL (first real-data path)
```bash
python -m celestial_triage.cli ingest-jsonl --input sample_data/example.jsonl
```

This path is schema-hardened for imperfect inputs:
- malformed JSONL lines are skipped with warnings
- missing source identifiers are skipped with warnings
- partial records use fallback normalization where possible
- unusable records (e.g., missing/invalid coordinates) are skipped

## Ingest from Lasair API (live external source)
Set token:
```bash
export LASAIR_API_TOKEN="your_token_here"
```

Run:
```bash
python -m celestial_triage.cli ingest-lasair --limit 100 --query "objectId:*" --days-back 3
# or pass token directly
python -m celestial_triage.cli ingest-lasair --token "$LASAIR_API_TOKEN" --limit 50 --days-back 2
```

Behavior:
- API failures and rate limits are handled gracefully with logs
- malformed records are skipped safely through the normalization-safe pipeline
- ingested detections flow into candidate linking, features, detector scoring, and retention via existing commands


## Run pipeline
```bash
python -m celestial_triage.cli run-pipeline
```

## Scenario evaluation report (dev/demo)
```bash
python -m celestial_triage.cli scenario-report
```

## List top candidates
```bash
python -m celestial_triage.cli top-candidates --limit 20
```

### Export top candidates
```bash
python -m celestial_triage.cli top-candidates --limit 50 --export csv --output top_candidates.csv
python -m celestial_triage.cli top-candidates --limit 50 --export json --output top_candidates.json
```

## Launch UI
```bash
python -m celestial_triage.cli launch-ui
# or directly:
streamlit run src/celestial_triage/ui/dashboard.py
```

## One-command smoke test
```bash
./scripts/smoke_test.sh
```

## CLI help
```bash
python -m celestial_triage.cli --help
```

## Lightweight developer tooling
- `ruff` and `black` config is in `pyproject.toml`
- `pytest` config is in `pyproject.toml`

## Known limitations
- Uses mock feed only (no live broker integration yet)
- Orbit fitting/hyperbolic logic are placeholders
- Rule-based scoring only (transparent, non-ML v1)
- UI is intentionally minimal for analyst workflow validation

## Next steps
- Add first real broker adapter implementation
- Improve orbital features and temporal linking
- Add migration tooling for PostgreSQL
- Add richer analyst review/audit workflow

## Disclaimer
This system ranks unusual astronomical candidates for review. It does **not** assert extraordinary identifications or definitive classifications.
