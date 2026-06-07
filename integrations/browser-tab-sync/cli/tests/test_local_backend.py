from pathlib import Path

from homebase_bts.backends.local import LocalBackend
from homebase_bts.models import Profile
from homebase_bts.reconcile import plan


def _profile() -> Profile:
    return Profile.model_validate(
        {
            "schema": 1,
            "id": "vacation",
            "tabs": [
                {"url": "https://maps.google.com/"},
                {"url": "https://www.google.com/travel/flights"},
            ],
        }
    )


def test_apply_loop_is_idempotent(tmp_path: Path):
    backend = LocalBackend(tmp_path / "sim.json")
    prof = _profile()

    first = plan(prof, backend.snapshot(prof.id))
    assert (first.group, first.created, first.existing) == ("new", 2, 0)
    backend.commit(prof, first)

    second = plan(prof, backend.snapshot(prof.id))
    assert (second.group, second.created, second.existing) == ("existing", 0, 2)
    backend.commit(prof, second)

    snap = backend.snapshot(prof.id)
    assert snap is not None
    assert len(snap.tabs) == 2
    assert {t.url for t in snap.tabs} == {
        "https://maps.google.com/",
        "https://www.google.com/travel/flights",
    }


def test_adding_a_tab_creates_only_the_new_one(tmp_path: Path):
    backend = LocalBackend(tmp_path / "sim.json")
    prof = _profile()
    backend.commit(prof, plan(prof, backend.snapshot(prof.id)))

    grown = Profile.model_validate(
        {
            "schema": 1,
            "id": "vacation",
            "tabs": [
                {"url": "https://maps.google.com/"},
                {"url": "https://www.google.com/travel/flights"},
                {"url": "https://www.google.com/travel/hotels"},
            ],
        }
    )
    p = plan(grown, backend.snapshot(grown.id))
    assert (p.created, p.existing) == (1, 2)
