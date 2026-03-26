SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_events (
  raw_event_id TEXT PRIMARY KEY,
  broker_name TEXT NOT NULL,
  source_id TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  ingest_time TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS detections (
  detection_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  broker_name TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  ra REAL NOT NULL,
  dec REAL NOT NULL,
  magnitude REAL NOT NULL,
  magnitude_change REAL NOT NULL,
  moving_flag INTEGER NOT NULL,
  class_label TEXT NOT NULL,
  class_confidence REAL NOT NULL,
  catalog_match_status TEXT NOT NULL,
  raw_payload_reference TEXT NOT NULL,
  ingest_time TEXT NOT NULL,
  mock_archetype_label TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
  candidate_id TEXT PRIMARY KEY,
  source_id TEXT UNIQUE NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  detection_count INTEGER NOT NULL,
  average_ra REAL NOT NULL,
  average_dec REAL NOT NULL,
  current_status TEXT NOT NULL,
  review_status TEXT NOT NULL,
  mock_archetype_label TEXT,
  tags TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS candidate_detections (
  candidate_id TEXT NOT NULL,
  detection_id TEXT NOT NULL,
  PRIMARY KEY(candidate_id, detection_id)
);

CREATE TABLE IF NOT EXISTS shared_features (
  candidate_id TEXT PRIMARY KEY,
  detection_count INTEGER,
  first_seen TEXT,
  last_seen TEXT,
  detection_span_hours REAL,
  avg_magnitude REAL,
  mag_delta_abs REAL,
  brightness_trend REAL,
  moving_fraction REAL,
  motion_rate_deg_per_hour REAL,
  motion_consistency_placeholder REAL,
  direction_consistency_placeholder REAL,
  heading_deg_placeholder REAL,
  heading_change_consistency REAL,
  path_smoothness_placeholder REAL,
  trajectory_quality REAL,
  poor_catalog_fraction REAL,
  avg_class_confidence REAL,
  angular_motion_placeholder REAL,
  orbit_fit_quality REAL,
  eccentricity_placeholder REAL,
  hyperbolic_likelihood REAL,
  inbound_outbound_placeholder TEXT,
  orbit_fit_placeholder REAL,
  hyperbolic_likelihood_placeholder REAL,
  anomaly_index_placeholder REAL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS detector_scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  detector_name TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  score REAL NOT NULL,
  score_band TEXT NOT NULL,
  reasons_json TEXT NOT NULL,
  version TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
  candidate_id TEXT PRIMARY KEY,
  reviewed_flag INTEGER NOT NULL,
  review_state TEXT,
  reviewed_by TEXT,
  reviewed_at TEXT,
  tags TEXT,
  analyst_notes TEXT
);

CREATE TABLE IF NOT EXISTS archive_policies (
  candidate_id TEXT PRIMARY KEY,
  retention_tier TEXT NOT NULL,
  keep_raw_payload INTEGER NOT NULL,
  keep_derived_products INTEGER NOT NULL,
  expiration_date TEXT,
  rationale TEXT NOT NULL,
  decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS image_assets (
  image_id TEXT PRIMARY KEY,
  detection_id TEXT,
  candidate_id TEXT,
  source_id TEXT,
  kind TEXT NOT NULL,
  broker_name TEXT,
  source_field TEXT,
  remote_url TEXT NOT NULL,
  local_path TEXT,
  fetch_status TEXT NOT NULL,
  error_message TEXT,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(detection_id, kind, remote_url)
);

CREATE TABLE IF NOT EXISTS plate_solves (
  solve_id TEXT PRIMARY KEY,
  image_path TEXT NOT NULL,
  status TEXT NOT NULL,
  ra_center REAL,
  dec_center REAL,
  field_width_deg REAL,
  field_height_deg REAL,
  orientation_deg REAL,
  pixel_scale_arcsec REAL,
  backend TEXT NOT NULL,
  job_id TEXT,
  error_message TEXT,
  metadata_json TEXT,
  solved_at TEXT NOT NULL,
  candidate_id TEXT,
  FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_plate_solves_coords ON plate_solves(ra_center, dec_center) WHERE ra_center IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_plate_solves_candidate ON plate_solves(candidate_id);
"""
