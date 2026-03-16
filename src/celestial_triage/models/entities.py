from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class RawEvent:
    raw_event_id: str
    broker_name: str
    source_id: str
    timestamp: datetime
    payload: dict[str, Any]


@dataclass
class NormalizedDetection:
    detection_id: str
    source_id: str
    broker_name: str
    timestamp: datetime
    ra: float
    dec: float
    magnitude: float
    magnitude_change: float
    moving_flag: bool
    class_label: str
    class_confidence: float
    catalog_match_status: str
    raw_payload_reference: str
    ingest_time: datetime


@dataclass
class CandidateObject:
    candidate_id: str
    source_id: str
    first_seen: datetime
    last_seen: datetime
    detection_count: int
    average_ra: float
    average_dec: float
    current_status: str = "active"
    review_status: str = "unreviewed"
    tags: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class DetectorScore:
    detector_name: str
    candidate_id: str
    score: float
    score_band: str
    reasons: list[str]
    version: str
    created_at: datetime


@dataclass
class ReviewState:
    candidate_id: str
    reviewed_flag: bool = False
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)
    analyst_notes: str = ""


@dataclass
class ArchiveDecision:
    candidate_id: str
    retention_tier: str
    keep_raw_payload: bool
    keep_derived_products: bool
    expiration_date: Optional[datetime]
    rationale: str
