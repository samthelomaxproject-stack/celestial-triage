# Plate Solving Guide

Image-first workflow for celestial triage.

## Overview

Plate solving converts sky images to coordinates (RA/DEC), enabling image-first analysis workflows.

**Flow:**
```
Image → Plate Solve → RA/DEC + Field metadata → Candidate creation/linkage → Normal triage
```

## Setup

### 1. Register for Astrometry.net API Key

Visit: http://nova.astrometry.net/api_help

1. Create account
2. Generate API key
3. Copy key

### 2. Configure Environment

```bash
export ASTROMETRY_API_KEY=your_api_key_here
```

Or add to your shell profile (`.zshrc`, `.bashrc`):
```bash
echo 'export ASTROMETRY_API_KEY=your_key' >> ~/.zshrc
```

## Usage

### CLI Mode

```bash
celestial-triage plate-solve --input path/to/image.fits --create-candidate
```

**Options:**
- `--input` (required) - Image file path
- `--create-candidate` - Create or link to candidate on success
- `--backend` - Solver (default: `astrometry.net`)
- `--timeout` - Max solve time seconds (default: 300)
- `--scale-low`, `--scale-high` - Pixel scale hints (arcsec/pixel)
- `--link-radius-deg` - Nearby candidate search radius (default: 0.01° ≈ 36")

**Example output:**
```
Solving image: test_image.fits
Backend: astrometry.net

Status: success
RA:  123.456789°
DEC: -45.123456°
Field: 30.00' × 30.00'
Scale: 1.500"/pixel
Orientation: 15.25°

Created new candidate: img_20260326_023045_a1b2c3d4
Solve stored: solve_20260326_023045_e5f6g7h8
Job ID: 12345678
```

### Mac App Mode

1. Launch Mac app: `python3 -m celestial_triage.macapp.desktop`
2. Click **"Solve Image..."** button (left panel, next to Refresh)
3. Select sky image file (FITS/PNG/JPG)
4. Wait for solve (progress dialog shows)
5. View result notification
6. New candidate appears in queue automatically
7. Click candidate → see Context Panel with solved coordinates

## Behavior

### Candidate Creation/Linkage

**When `--create-candidate` is used:**

1. **Search nearby candidates** (within `--link-radius-deg`, default 0.01° ≈ 36")
   
2. **If nearby candidate found:**
   - Links solve to existing candidate
   - Shows distance in output
   - Preserves existing candidate data
   
3. **If no nearby candidate:**
   - Creates new image-origin candidate
   - Generates synthetic detection with:
     - `broker_name='plate_solve'`
     - `class_label='image_solve'`
     - `magnitude=99.0` (unknown)
   - New candidate appears in normal workflow

### Solve Metadata Storage

All solves are stored in `plate_solves` table:
- `solve_id` - Unique identifier
- `image_path` - Original image path
- `status` - success/failed/timeout/error
- `ra_center`, `dec_center` - Field center
- `field_width_deg`, `field_height_deg` - Field dimensions
- `orientation_deg` - Image rotation
- `pixel_scale_arcsec` - Scale factor
- `backend` - Solver used
- `job_id` - Backend job reference
- `candidate_id` - Linked candidate (if any)
- `solved_at` - Timestamp

## Supported Image Formats

- **FITS** - Astronomical standard (preferred)
- **PNG** - Common image format
- **JPG/JPEG** - Common image format

**Note:** FITS files typically solve faster and more reliably due to embedded metadata.

## Solve Time

**Typical solve times:**
- Simple fields (sparse stars): 30-60 seconds
- Complex fields (crowded stars): 60-180 seconds
- Difficult cases: Up to 300 seconds (timeout)

**Factors affecting solve time:**
- Image quality
- Star density
- Field size
- Presence of metadata hints (pixel scale)

## Error Handling

### Missing API Key
```
Error: Astrometry.net API key required. Set ASTROMETRY_API_KEY...
```
**Fix:** Set `ASTROMETRY_API_KEY` environment variable

### Solve Timeout
```
Status: timeout
Error: Solve timed out after 300 seconds
Job ID: 12345678
```
**Fix:** 
- Increase `--timeout`
- Add scale hints: `--scale-low 1.0 --scale-high 2.0`
- Check image quality

### Solve Failed
```
Status: failed
Error: No solution found
Job ID: 12345678
```
**Causes:**
- Image too noisy
- Too few stars
- Non-sky image
- Extreme field size

**Fix:**
- Verify image is a real sky image
- Check image contains visible stars
- Try adding scale hints if known

### File Not Found
```
Error: Image file not found: /path/to/image.fits
```
**Fix:** Check file path and permissions

## Backend Architecture

### Current: Astrometry.net Remote API

**Pros:**
- No local installation required
- Proven solver
- Handles wide range of image types

**Cons:**
- Requires internet connection
- Requires API key registration
- Solve time depends on API load
- Data leaves local system

### Future: Local Solver Support

The module is designed to support local backends:
```python
def solve_image(image_path, backend="local_astrometry", **kwargs)
```

**Planned local backends:**
- Local Astrometry.net installation
- astrometry.cfg-based solving
- Custom solver integrations

**Design allows swapping backends without changing CLI/UI code.**

## Integration with Triage Workflow

Plate-solved candidates are **first-class citizens** in the triage system:

✅ Appear in candidate queue  
✅ Have Context Panel (RA/DEC, field info)  
✅ Show in Sky Map  
✅ Support review workflow (state, tags, notes)  
✅ Can be scored by detector layers (if features present)  
✅ Can be exported/bundled  

**Distinguishing features:**
- `broker_name='plate_solve'`
- `class_label='image_solve'`
- Source appears in provenance as "plate_solve:1"

## Limitations

- Requires internet for Astrometry.net backend
- Solve time varies (30s-5min)
- No local solver option yet
- Image-origin candidates have limited features (no light curve, motion history)
- Magnitude set to 99.0 (unknown)

## Examples

### CLI: Solve and create candidate
```bash
celestial-triage plate-solve \
  --input telescope_capture.fits \
  --create-candidate \
  --scale-low 1.0 \
  --scale-high 2.0
```

### CLI: Solve only (no candidate creation)
```bash
celestial-triage plate-solve --input image.fits
```

### Mac App: Interactive workflow
1. Click "Solve Image..."
2. Navigate to `~/telescope_data/capture_001.fits`
3. Click Open
4. Wait for solve
5. New candidate "img_20260326_..." appears
6. Click candidate → see RA: 123.456789°, DEC: -45.123456°
7. Review Context Panel, images, Sky Map position
