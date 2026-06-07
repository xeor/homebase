from homebase_bts.models import Profile
from homebase_bts.protocol import ProfileSnapshot, SnapshotTab
from homebase_bts.reconcile import plan


def _profile(**over) -> Profile:
    data = {
        "schema": 1,
        "id": "vacation",
        "title": "Vacation",
        "tabs": [
            {"url": "https://maps.google.com/"},
            {"url": "https://www.google.com/travel/flights"},
        ],
    }
    data.update(over)
    return Profile.model_validate(data)


def _snapshot(*urls: str) -> ProfileSnapshot:
    tabs = [SnapshotTab(browser_tab_id=i, url=u, index=i) for i, u in enumerate(urls)]
    return ProfileSnapshot(profile_id="vacation", browser="local", group_id=1, tabs=tabs)


def _snapshot_tabs(*tabs: SnapshotTab) -> ProfileSnapshot:
    return ProfileSnapshot(profile_id="vacation", browser="local", group_id=1, tabs=list(tabs))


def test_no_actual_state_creates_all():
    p = plan(_profile(), None)
    assert p.group == "new"
    assert (p.created, p.existing, p.moved) == (2, 0, 0)


def test_all_present_reuses():
    snap = _snapshot("https://maps.google.com/", "https://www.google.com/travel/flights")
    p = plan(_profile(), snap)
    assert p.group == "existing"
    assert (p.created, p.existing) == (0, 2)


def test_partial_present_creates_missing():
    snap = _snapshot("https://maps.google.com/")
    p = plan(_profile(), snap)
    assert (p.created, p.existing) == (1, 1)


def test_normalized_url_matching_ignores_tracking_params():
    snap = _snapshot(
        "https://maps.google.com/?utm_source=x", "https://www.google.com/travel/flights"
    )
    p = plan(_profile(), snap)
    assert p.existing == 2


def test_duplicate_actual_tab_matched_once():
    snap = _snapshot("https://maps.google.com/", "https://maps.google.com/")
    p = plan(_profile(), snap)
    # only one of the two duplicate actual tabs satisfies "maps"; flights is created
    assert (p.created, p.existing) == (1, 1)


def test_title_url_matching_reuses_matching_title():
    prof = _profile(
        tabs=[{"url": "https://example.com/old", "title": "Docs"}],
        sync={"match": "title-url"},
    )
    snap = _snapshot_tabs(
        SnapshotTab(browser_tab_id=1, url="https://example.com/new", title="Docs", index=0)
    )
    p = plan(prof, snap)
    assert (p.created, p.existing) == (0, 1)


def test_title_url_matching_falls_back_to_normalized_url():
    prof = _profile(tabs=[{"url": "https://example.com/docs"}], sync={"match": "title-url"})
    snap = _snapshot("https://example.com/docs?utm_source=x")
    p = plan(prof, snap)
    assert (p.created, p.existing) == (0, 1)


def test_exact_url_matching_ignores_title():
    prof = _profile(
        tabs=[{"url": "https://example.com/old", "title": "Docs"}],
        sync={"match": "exact-url"},
    )
    snap = _snapshot_tabs(
        SnapshotTab(browser_tab_id=1, url="https://example.com/new", title="Docs", index=0)
    )
    p = plan(prof, snap)
    assert (p.created, p.existing) == (1, 0)
