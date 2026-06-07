from homebase_bts.models import Profile
from homebase_bts.protocol import ProfileSnapshot, SnapshotGroup, SnapshotTab
from homebase_bts.reconcile import merge_snapshot


def _profile(**over) -> Profile:
    data = {
        "schema": 1,
        "id": "vacation",
        "title": "Vacation",
        "group": {"title": "Vacation", "color": "cyan"},
        "tabs": [
            {"url": "https://maps.google.com/"},
            {"url": "https://www.google.com/travel/flights"},
        ],
    }
    data.update(over)
    return Profile.model_validate(data)


def _snap(tabs: list[SnapshotTab], group: SnapshotGroup | None = None) -> ProfileSnapshot:
    return ProfileSnapshot(
        profile_id="vacation", browser="chrome", group_id=1, group=group, tabs=tabs
    )


def test_no_change_is_noop():
    snap = _snap(
        [
            SnapshotTab(
                browser_tab_id=1,
                url="https://maps.google.com/x",
                managed_url="https://maps.google.com/",
                index=0,
            ),
            SnapshotTab(browser_tab_id=2, url="https://www.google.com/travel/flights", index=1),
        ]
    )
    merged, summary = merge_snapshot(_profile(), snap)
    assert not summary.changed
    assert [t.url for t in merged.tabs] == [
        "https://maps.google.com/",
        "https://www.google.com/travel/flights",
    ]


def test_managed_url_survives_redirect():
    # live url drifted, but managed_url keeps identity -> matched, clean url preserved
    snap = _snap(
        [
            SnapshotTab(
                browser_tab_id=1,
                url="https://www.google.com/maps/@59,10,12z",
                managed_url="https://maps.google.com/",
                index=0,
            ),
            SnapshotTab(browser_tab_id=2, url="https://www.google.com/travel/flights", index=1),
        ]
    )
    merged, summary = merge_snapshot(_profile(), snap)
    assert summary.added == 0
    assert merged.tabs[0].url == "https://maps.google.com/"  # preserved, not the drifted url


def test_new_tab_is_added_in_order():
    snap = _snap(
        [
            SnapshotTab(browser_tab_id=1, url="https://maps.google.com/", index=0),
            SnapshotTab(browser_tab_id=3, url="https://news.ycombinator.com/", index=1),
            SnapshotTab(browser_tab_id=2, url="https://www.google.com/travel/flights", index=2),
        ]
    )
    merged, summary = merge_snapshot(_profile(), snap)
    assert summary.added == 1
    assert [t.url for t in merged.tabs] == [
        "https://maps.google.com/",
        "https://news.ycombinator.com/",
        "https://www.google.com/travel/flights",
    ]


def test_closed_tab_kept_when_delete_missing_false():
    prof = _profile(sync={"delete_missing": False})
    snap = _snap([SnapshotTab(browser_tab_id=1, url="https://maps.google.com/", index=0)])
    merged, summary = merge_snapshot(prof, snap)
    assert summary.removed == 0
    assert {t.url for t in merged.tabs} == {
        "https://maps.google.com/",
        "https://www.google.com/travel/flights",
    }  # flights kept


def test_closed_tab_kept_by_default():
    snap = _snap([SnapshotTab(browser_tab_id=1, url="https://maps.google.com/", index=0)])
    merged, summary = merge_snapshot(_profile(), snap)
    assert summary.removed == 0
    assert {t.url for t in merged.tabs} == {
        "https://maps.google.com/",
        "https://www.google.com/travel/flights",
    }


def test_closed_tab_removed_when_delete_missing_true():
    snap = _snap([SnapshotTab(browser_tab_id=1, url="https://maps.google.com/", index=0)])
    merged, summary = merge_snapshot(_profile(sync={"delete_missing": True}), snap)
    assert summary.removed == 1
    assert [t.url for t in merged.tabs] == ["https://maps.google.com/"]


def test_group_meta_change():
    snap = _snap(
        [SnapshotTab(browser_tab_id=1, url="https://maps.google.com/", index=0)],
        group=SnapshotGroup(title="Holiday", color="red", collapsed=True),
    )
    merged, summary = merge_snapshot(_profile(sync={"delete_missing": True}), snap)
    assert summary.group_changed
    assert merged.group.title == "Holiday"
    assert merged.group.color.value == "red"
    assert merged.group.collapsed is True
