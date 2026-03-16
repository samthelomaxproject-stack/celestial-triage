# celestial-triage

Celestial Triage is a layered analyst system for astronomical alert triage.

It ingests broker alerts, normalizes them into a common detection model, groups detections into candidate objects, scores those candidates across multiple detector domains, builds interpretation/conflict summaries, assigns follow-up priority, and supports analyst review/export workflows.

The project includes:
- a backend triage engine (storage + scoring + workflow logic)
- a CLI boundary for reproducible operations
- a Mac desktop analyst console on top of the CLI/backend
- image/cutout asset linkage for science/reference/difference views when available

---

## What problem this solves

Modern alert streams produce more objects than analysts can inspect manually. Celestial Triage helps by:

- standardizing heterogeneous alert payloads into one canonical schema
- ranking candidates by detector evidence and follow-up urgency
- exposing interpretation/conflict context instead of a single opaque label
- preserving analyst state (review state, tags, notes)
- generating structured exports/bundles for handoff workflows

It is a **triage and prioritization system** — not a claim engine.

---

## System architecture

### End-to-end pipeline

Broker ingestion  
↓  
Normalization  
↓  
Candidate association  
↓  
Feature extraction  
↓  
Detector layers  
↓  
Interpretation/conflict analysis  
↓  
Follow-up prioritization  
↓  
Analyst review workflow  
↓  
Export / bundle generation  
↓  
Mac desktop analyst console

### Components and relationships

- **Backend engine** (`src/celestial_triage/...`)
  - data model, SQLite persistence, ingestion adapters, feature extraction, detector scoring, interpretation/follow-up logic, retention and review persistence.
- **CLI interface** (`python3 -m celestial_triage.cli ...`)
  - operational boundary for all approved actions.
- **Mac desktop UI** (`src/celestial_triage/macapp/desktop.py`)
  - analyst console that reads backend data and triggers approved CLI actions through a safe runner.
- **Image asset layer**
  - extracts/stores image references from payloads and links them to detections/candidates for UI display.

---

## Repository layout (high level)

- `src/celestial_triage/cli.py` — CLI command surface
- `src/celestial_triage/storage/` — schema + DB access
- `src/celestial_triage/ingest/` — ingest adapters + normalization
- `src/celestial_triage/features/` — candidate-level feature extraction
- `src/celestial_triage/detectors/` — detector scoring modules
- `src/celestial_triage/scoring/` — interpretation, follow-up, evaluation
- `src/celestial_triage/ui/dashboard.py` — Streamlit dashboard (transition path)
- `src/celestial_triage/macapp/desktop.py` — Mac desktop analyst console
- `src/celestial_triage/macapp/runner.py` — safe CLI action mapping layer

---

## Installation

```bash
git clone https://github.com/samthelomaxproject-stack/celestial-triage.git
cd celestial-triage

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

If you prefer non-editable install for runtime only:

```bash
pip install .
```

---

## Quick start

```bash
python3 -m celestial_triage.cli init-db
python3 -m celestial_triage.cli seed-mock --count 120
python3 -m celestial_triage.cli run-pipeline
python3 -m celestial_triage.cli top-candidates --limit 20
```

Optional next step:

```bash
python3 -m celestial_triage.cli followup-report --limit 20
```

---

## Broker ingestion (Lasair)

Celestial Triage supports two Lasair broker domains.

### 1) ZTF broker
- Domain: `https://lasair-ztf.lsst.ac.uk`
- Typical mode: `ztf`
- Request format: `{"query": ...}`

Example:

```bash
export LASAIR_API_TOKEN="<your_token>"
python3 -m celestial_triage.cli ingest-lasair \
  --lasair-mode ztf \
  --base-url https://lasair-ztf.lsst.ac.uk/api \
  --query "objectId:*" \
  --days-back 3 \
  --limit 50
```

### 2) LSST / Rubin broker
- Domain: `https://lasair.lsst.ac.uk`
- Typical mode: `lsst`
- Request format: `selected / tables / conditions`

Example:

```bash
export LASAIR_API_TOKEN="<your_token>"
python3 -m celestial_triage.cli ingest-lasair \
  --lasair-mode lsst \
  --base-url https://lasair.lsst.ac.uk/api \
  --selected "diaObjectId, ra, decl" \
  --tables objects \
  --conditions "1=1" \
  --limit 10
```

Optional automatic object-detail/cutout retrieval after ingest:

```bash
python3 -m celestial_triage.cli ingest-lasair \
  --lasair-mode lsst \
  --base-url https://lasair.lsst.ac.uk/api \
  --selected "diaObjectId, ra, decl" \
  --tables objects \
  --conditions "1=1" \
  --limit 25 \
  --fetch-cutouts
```

### Higher total ingest with spaced requests

`--limit` is the **total desired** results. The ingest path internally batches and spaces requests:

- `--batch-size`: per-request size
- `--request-delay`: seconds between broker requests
- `--max-retries`: 429 backoff retry count (exponential)

Example (total 50, 5 requests of 10, 3s spacing):

```bash
python3 -m celestial_triage.cli ingest-lasair \
  --lasair-mode lsst \
  --base-url https://lasair.lsst.ac.uk/api \
  --selected "*" \
  --tables objects \
  --conditions "1=1" \
  --limit 50 \
  --batch-size 10 \
  --request-delay 3 \
  --max-retries 3
```

### Token requirements

Tokens are broker/domain scoped. A token from one broker UI may fail against the other domain.

If you get `401 Invalid token`, verify:
- token source (ZTF UI vs LSST UI)
- `--lasair-mode`
- `--base-url`

---

## Mac desktop analyst console

Location:
- `src/celestial_triage/macapp/desktop.py`
- `src/celestial_triage/macapp/runner.py`

### Verified macOS runtime path

This project has been verified with a Tk-capable Python 3.12 environment:

```bash
brew install python@3.12
brew install python-tk@3.12

python3.12 -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt

export PYTHONPATH=src
python3 -m celestial_triage.macapp.desktop
```

> Note: some Python builds may not include `_tkinter` (for example `python@3.14` on this host during validation). Use the Tk-capable 3.12 runtime above if you see tkinter import errors.

Launch (Python desktop mode):

```bash
python3 -m celestial_triage.macapp.desktop
```

Package as a native macOS `.app` bundle (while keeping Python mode available):

```bash
./scripts/package_macos_app.sh
```

Expected output bundle:

```bash
dist/CelestialTriage.app
```

### UI layout

- **Left pane:** candidate queue + review filter
- **Center pane:** candidate detail, detector scores, interpretation/conflict summary, trajectory summary, timeline/provenance, follow-up priority
- **Right pane:** image panel + command/action tabs + execution logs

### Safe command execution model

The desktop app does **not** execute arbitrary shell commands.

It uses `SafeCliRunner` (`runner.py`) to map form inputs to an approved CLI allowlist only.

---

## Image asset support

Image references discovered in broker payloads are stored in `image_assets` and linked to detections/candidates.

### Supported image types
- `science`
- `reference` / `template`
- `difference`

### Data model highlights (`image_assets`)
- linkage: `detection_id`, `candidate_id`, `source_id`
- type: `kind`
- location: `remote_url`, optional `local_path`
- status: `fetch_status`, `error_message`
- metadata: `metadata_json`

### Layered imaging strategy

Celestial Triage now uses layered image sourcing in this priority order:

1. **Broker cutouts** (`science`, `reference`, `difference`) when available
2. **Pan-STARRS survey context** (`survey_context_panstarrs`)
3. **SkyView DSS fallback** (`survey_context_skyview`) when Pan-STARRS is unavailable

`ingest-lasair --fetch-cutouts` performs broker detail lookup for image/cutout references.
Survey context retrieval is layered and non-fatal: if one source fails, ingest continues.

### Preview generation + storage

When embedded/base64 cutout payloads are present, Celestial Triage attempts to decode and render local PNG previews automatically.
Survey context images are also saved locally as PNG.

Preview storage location:
- default: `./image_previews/<candidate_id>/...png`
- override with env: `CELESTIAL_TRIAGE_PREVIEW_DIR`

Typical files:
- `image_previews/<candidate_id>/survey_context_panstarrs.png`
- `image_previews/<candidate_id>/survey_context_skyview.png`

### Mac app image panel behavior

The Mac app image panel:
- auto-renders **all available images** for the selected candidate
- shows broker image assets first when available
- shows Pan-STARRS context image when available
- shows SkyView DSS fallback when Pan-STARRS is unavailable
- uses a vertical scrollbar for multi-image candidates
- prefers local preview PNGs for in-app display
- falls back to opening remote URLs when only remote links exist

Current limitations:
- LSST object payload/detail paths may not include broker cutout URLs or embedded stamp data for many objects.
- Pan-STARRS does not cover all sky locations; some Rubin/LSST candidates may be out of coverage.
- SkyView response behavior can vary (direct image vs HTML link flow).
- cutout lookup/render failures do not fail primary ingest; they are logged and skipped.

---

## CLI command reference

All major workflows are exposed via:

```bash
python3 -m celestial_triage.cli <command> [options]
```

### Core commands

- `init-db` — initialize SQLite schema
- `seed-mock` — generate mock events and normalized detections
- `ingest-jsonl` — ingest external JSONL records
- `ingest-lasair` — ingest live Lasair API records (ZTF/LSST modes)
- `run-pipeline` — run feature extraction + detector scoring + retention
- `top-candidates` — list highest-ranked candidates
- `scenario-report` — summarize mock archetype vs detector outcomes
- `update-review` — set review state, tags, notes
- `followup-report` — report candidates by follow-up priority
- `export-candidates` — export filtered candidate handoff data (json/csv/md)
- `bundle-cases` — generate analyst bundle directory (summary + optional details)
- `launch-ui` — launch Streamlit dashboard

See full options:

```bash
python3 -m celestial_triage.cli --help
python3 -m celestial_triage.cli ingest-lasair --help
```

---

## Analyst workflow

### Review states
- `new`
- `reviewing`
- `follow-up`
- `dismissed`

### Review metadata
- tags (comma-separated)
- analyst notes

### Triage outputs surfaced to analysts
- detector score map
- interpretation summary (primary interpretation + conflict context)
- follow-up priority + reasons
- provenance/timeline context
- retention tier context

### Handoff outputs
- `export-candidates` for structured exports
- `bundle-cases` for analyst package directories

---

## Streamlit dashboard (transition path)

Streamlit remains available during desktop migration:

```bash
python3 -m celestial_triage.cli launch-ui
# or
streamlit run src/celestial_triage/ui/dashboard.py
```

---

## Development and testing

Run tests:

```bash
pytest -q
```

Run smoke test:

```bash
./scripts/smoke_test.sh
```

Compile check:

```bash
python3 -m compileall -q src
```

---

## Troubleshooting

### Problem: `ModuleNotFoundError: No module named 'celestial_triage'`
Cause:
- package not installed in current environment, or running without package path.

Solution:
```bash
pip install -e .
# or if running source-layout directly
export PYTHONPATH=src
```

### Problem: `Invalid Lasair token`
Cause:
- token/domain mismatch (for example LSST token used against ZTF endpoint).

Solution:
- use matching `--lasair-mode` and `--base-url`:
  - LSST: `--lasair-mode lsst --base-url https://lasair.lsst.ac.uk/api`
  - ZTF: `--lasair-mode ztf --base-url https://lasair-ztf.lsst.ac.uk/api`

### Problem: `python: command not found`
Solution:
```bash
python3 ...
```

### Problem: `ModuleNotFoundError: No module named '_tkinter'`
Cause:
- current Python build does not include Tk runtime bindings.

Solution (verified):
```bash
brew install python@3.12
brew install python-tk@3.12
python3.12 -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
python3 -m celestial_triage.macapp.desktop
```

### Problem: image panel is empty
Cause:
- current broker query payload does not include cutout/image URLs.

Solution:
- expand selected fields or use payload/query paths that include cutout references.

---

## Roadmap

Planned/desired improvements:

- sky map visualization for candidate tracks
- automatic image anomaly heuristics/classification
- Android companion app for analyst workflows
- real-time broker streaming ingestion paths
- improved orbit fitting and physical consistency modeling

---

## Disclaimer

Celestial Triage ranks and organizes candidates for analyst review.
It does **not** make definitive extraordinary-object claims.
