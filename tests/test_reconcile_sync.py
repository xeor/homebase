from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from homebase.ui.sync import reconcile


@dataclass
class _Row:
    path: Path
    stale: bool = False
    last_reconciled_ts: int = 0
    last_ts: int = 0
    dirty: str = ""


class _App:
    def __init__(self) -> None:
        self.active_rows = [
            _Row(Path("/tmp/a"), stale=True, last_reconciled_ts=10, last_ts=10, dirty="~"),
            _Row(Path("/tmp/b"), stale=False, last_reconciled_ts=20, last_ts=20, dirty=""),
        ]
        self.archived_rows = []
        self.reconcile_config = {
            "active": {
                "interval_s": 10.0,
                "batch_size": 2,
                "parallelism": 2,
                "use_usage_score": False,
                "usage_weight": 0.0,
                "stale_boost": False,
            }
        }
        self.row_usage_score = {Path("/tmp/a"): 100.0, Path("/tmp/b"): 0.0}
        self.row_usage_hits = {Path("/tmp/a"): 20, Path("/tmp/b"): 0}
        self.row_usage_last_used_ts = {Path("/tmp/a"): 100, Path("/tmp/b"): 0}


def test_effective_reconcile_values_honor_profile_fields() -> None:
    app = _App()
    assert reconcile.effective_reconcile_wait_s(app, "active") == 10.0
    assert reconcile.effective_reconcile_parallelism(app, "active") == 2
    assert reconcile.effective_reconcile_batch_size(app, "active") == 2


def test_pick_reconcile_candidates_honors_usage_toggle() -> None:
    app = _App()
    app.active_rows[0].stale = False
    out = reconcile.pick_reconcile_candidates(
        app,
        "active",
        1,
        mode_active="active",
        now_ts=200,
        random_choices=lambda pool, weights, k: [pool[weights.index(max(weights))]],
    )
    assert out
    assert out[0].path == Path("/tmp/a")
