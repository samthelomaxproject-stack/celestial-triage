from celestial_triage.storage.retention import assign_retention_tier


def test_retention_assigns_hot_for_high_score():
    tier, *_ = assign_retention_tier(0.9, 2, False, 0.1, 0.2)
    assert tier == "hot"


def test_retention_assigns_disposable_for_low_score():
    tier, *_ = assign_retention_tier(0.1, 1, False, 0.0, 0.0)
    assert tier == "disposable"
