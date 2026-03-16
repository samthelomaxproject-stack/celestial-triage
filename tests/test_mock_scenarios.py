from celestial_triage.ingest.mock_feed import MockFeedAdapter


def test_mock_scenarios_cover_all_archetypes():
    feed = MockFeedAdapter(count=240)
    events = feed.fetch_events()
    labels = {e.payload.get("mock_archetype_label") for e in events}
    for archetype in MockFeedAdapter.ARCHETYPES:
        assert archetype in labels
