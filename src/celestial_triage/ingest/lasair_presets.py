from dataclasses import dataclass


@dataclass(frozen=True)
class LasairPreset:
    name: str
    query: str
    days_back: int
    limit: int
    description: str


PRESETS: dict[str, LasairPreset] = {
    "fast_movers": LasairPreset(
        name="fast_movers",
        query="is_moving:true AND dmag:>0.5",
        days_back=2,
        limit=150,
        description="Prioritize rapidly changing moving detections.",
    ),
    "iso_candidates": LasairPreset(
        name="iso_candidates",
        query="is_moving:true AND (match_status:no_match OR catalog_match:no_match)",
        days_back=5,
        limit=150,
        description="Moving detections with weak catalog matches for ISO triage.",
    ),
    "poor_catalog_matches": LasairPreset(
        name="poor_catalog_matches",
        query="(match_status:poor_match OR match_status:no_match)",
        days_back=4,
        limit=200,
        description="Records with poor/no catalog matching.",
    ),
    "bright_followup": LasairPreset(
        name="bright_followup",
        query="mag:<18.5",
        days_back=3,
        limit=120,
        description="Brighter detections suitable for follow-up.",
    ),
    "ambiguous_movers": LasairPreset(
        name="ambiguous_movers",
        query="is_moving:true AND confidence:<0.5",
        days_back=4,
        limit=160,
        description="Moving detections with weaker classifier confidence.",
    ),
}


def resolve_preset(name: str | None) -> LasairPreset | None:
    if not name:
        return None
    return PRESETS.get(name)
