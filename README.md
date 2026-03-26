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

**LSST and ZTF use separate API tokens.** They are not interchangeable.

Environment variables:
- `LASAIR_LSST_API_TOKEN` — for LSST mode (`--lasair-mode lsst`)
- `LASAIR_ZTF_API_TOKEN` — for ZTF mode (`--lasair-mode ztf`)

Broker-specific endpoints:
- LSST: `https://lasair.lsst.ac.uk/api`
- ZTF: `https://lasair-ztf.lsst.ac.uk/api`

If you get `401 Invalid token`:
- Verify you are using the correct token for the selected mode
- Check that `LASAIR_LSST_API_TOKEN` is set for LSST, or `LASAIR_ZTF_API_TOKEN` for ZTF
- Confirm `--lasair-mode` matches your token type
- Verify `--base-url` matches the token's broker domain

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

- **Left pane:** candidate queue + review filter + **Solve Image... button**
- **Center pane:** candidate detail, detector scores, interpretation/conflict summary, trajectory summary, timeline/provenance, follow-up priority
- **Right pane:** image panel + command/action tabs + execution logs

### Image-first workflow (Galileo-style)

The **"Solve Image..."** button enables sensor/image-first analysis:

1. Click **"Solve Image..."** in left panel
2. Select sky image (FITS, PNG, JPG)
3. System plate-solves image via Astrometry.net
4. If successful:
   - Extracts RA/DEC, field size, orientation
   - Creates new candidate OR links to nearby existing candidate
   - Candidate appears in queue immediately
5. Select candidate → normal Context Panel/Sky Map/Review workflow

**Use cases:**
- Analyze telescope/camera captures without broker ingestion
- Cross-reference external observations with candidate database
- Bootstrap triage from raw imaging data

**Requirements:**
- Astrometry.net API key (set `ASTROMETRY_API_KEY` env var)
- Register free at: http://nova.astrometry.net/api_help

### Safe command execution model

The desktop app does **not** execute arbitrary shell commands.

It uses `SafeCliRunner` (`runner.py`) to map form inputs to an approved CLI allowlist only.

---

## Image asset support

Image references discovered in broker payloads are stored in `image_assets` and linked to detections/candidates.

### Plate solving (image-first workflow)

**New capability:** Solve arbitrary sky images to coordinates using plate solving, then feed into candidate workflow.

**Use case:** Sensor/image-first analysis path (Galileo-style):
```
Image → Plate solve → RA/DEC → Candidate creation/association → Context/Review
```

**CLI command:**
```bash
celestial-triage plate-solve --input path/to/image.fits --create-candidate
```

**Backend support:**
- **Current:** Astrometry.net remote API (requires `ASTROMETRY_API_KEY`)
- **Future:** Local plate solver backends

**Behavior:**
1. Submit image to plate solving backend
2. Extract RA/DEC center, field size, orientation, pixel scale
3. Store solve metadata in `plate_solves` table
4. If `--create-candidate` specified:
   - Search for nearby candidates (within `--link-radius-deg`, default 0.01° ≈ 36")
   - If found: Link solve to existing candidate
   - If not: Create new image-origin candidate with synthetic detection
5. Solved candidates appear in normal triage workflow (Context Panel, Sky Map, Review)

**Solve result structure:**
- `ra_center`, `dec_center` - Field center coordinates
- `field_width_deg`, `field_height_deg` - Field dimensions
- `orientation_deg` - Image orientation
- `pixel_scale_arcsec` - Arcsec per pixel
- `status` - success/failed/timeout/error
- `backend` - Solver used
- `job_id` - Backend job reference

**Fail-soft:**
- Missing API key: Clear error, no crash
- Solve timeout: Graceful failure with job ID
- Solve failure: Preserved with error message
- Does not break existing broker/survey workflows

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

### Candidate context panel (Mac app)

The selected candidate includes a **Context Panel** optimized for quick analyst decision-making.

**Panel structure (hierarchical sections):**

1. **POSITION** - RA/DEC coordinates (always visible, high precision)
2. **CLASSIFICATION** - Primary interpretation + follow-up priority (key decision data)
3. **CONTEXT** - Field environment with quick-scan indicators:
   - 🟢/🟡/🔴 Field density (isolated/moderate/crowded)
   - ✓/✗/? Catalog match status
   - 🏠/∅/? Host association
   - ⚠ Nearest object (if <60 arcsec)
4. **PROVENANCE** - Detection sources and history count (compact)
   - includes linked plate-solve provenance when present:
     - plate_solve_count
     - latest solve timestamp
     - latest solver backend/status
5. **SUMMARY** - Natural-language concise explanation

**Quick-scan indicators** allow rapid pattern recognition without reading full text.

**Concise explanation** uses natural language instead of technical jargon (e.g., "Moderately crowded. Strong catalog match, likely host-associated. Interpreted as iso.")

**Sources:** Local data only (candidate/detection/image records, catalog match status, interpretation/follow-up summaries) - not external authoritative catalogs.

### Sky map panel (Mac app)

The Mac app now includes a **Sky Map (RA/DEC)** panel that:
- plots all plottable candidates (RA on x-axis, DEC on y-axis)
- colors points by follow-up priority (urgent/high/medium/low)
- emphasizes selected candidate point
- supports click-to-select via nearest-point selection
- syncs map selection back into candidate detail/queue context

Limitations (first pass):
- simple 2D RA/DEC projection (no advanced sky projection/wrap handling)
- no pan/zoom yet
- candidates without usable coordinates are skipped

### Mac app image panel behavior

The Mac app image panel:
- auto-renders **all available images** for the selected candidate
- keeps a stable display order:
  1) science
  2) reference
  3) difference
  4) survey_context_panstarrs
  5) survey_context_skyview
- collects and displays broker + Pan-STARRS + SkyView when available
- uses a vertical scrollbar for multi-image candidates
- prefers local preview PNGs for in-app display
- falls back to opening remote URLs when only remote links exist

Candidate marker/overlay behavior:
- draws a small broken-square target marker at image center for the selected candidate
- shows compact RA/DEC annotation overlay (analyst-style) on rendered images
- includes a **Show motion track** toggle in the image panel (default OFF)
- when motion track is OFF: marker + RA/DEC only
- when motion track is ON (multi-detection candidates): faint prior-position dots + last-segment direction arrow
- for one-detection candidates, no synthetic motion track is drawn
- assumes survey cutouts are centered on the candidate (true for SkyView, Pan-STARRS, and most broker stamps)
- future-ready structure supports RA/DEC → pixel mapping for precise positioning when needed

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
- **`plate-solve`** — solve image to RA/DEC coordinates (image-first workflow)
- `run-pipeline` — run feature extraction + detector scoring + retention
- `top-candidates` — list highest-ranked candidates
- `scenario-report` — summarize mock archetype vs detector outcomes
- `update-review` — set review state, tags, notes
- `followup-report` — report candidates by follow-up priority
- `export-candidates` — export filtered candidate handoff data (json/csv/md)
- `bundle-cases` — generate analyst bundle directory (summary + optional details)
- `launch-ui` — launch Streamlit dashboard

### Plate solving command

```bash
celestial-triage plate-solve --input image.fits --create-candidate
```

**Options:**
- `--input` (required) - Path to FITS or image file
- `--backend` - Solver backend (default: `astrometry.net`)
- `--api-key` - API key for remote solver (or set `ASTROMETRY_API_KEY` env)
- `--timeout` - Max solve time in seconds (default: 300)
- `--scale-low`, `--scale-high` - Pixel scale hints (arcsec/pixel)
- `--create-candidate` - Create or link to candidate on success
- `--link-radius-deg` - Radius for finding nearby candidates (default: 0.01°)

**Output:**
- RA/DEC center coordinates
- Field dimensions and orientation
- Pixel scale
- Candidate creation/linkage status

**Requirements:**
- Astrometry.net API key: http://nova.astrometry.net/api_help
- Set `ASTROMETRY_API_KEY` environment variable

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

Completed:
- ✅ Sky map visualization (RA/DEC 2D plot with priority coloring)
- ✅ Image-first plate solving workflow (Astrometry.net integration)
- ✅ Context Panel hierarchical refinements

Planned/desired improvements:
- Local plate solver backend support (avoid remote API dependency)
- Automatic image anomaly heuristics/classification
- Android companion app for analyst workflows
- Real-time broker streaming ingestion paths
- Improved orbit fitting and physical consistency modeling
- Pan/zoom on sky map
- Advanced sky projection handling

---

## Disclaimer

Celestial Triage ranks and organizes candidates for analyst review.
It does **not** make definitive extraordinary-object claims.
