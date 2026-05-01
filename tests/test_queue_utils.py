from __future__ import annotations

from pathlib import Path

from homebase.cache import queue as queue_utils


def test_reconcile_queue_push_sorts_by_priority_then_reason() -> None:
    q = []
    q = queue_utils.reconcile_queue_push(q, "active", "z", [Path("a")], 1)
    q = queue_utils.reconcile_queue_push(q, "active", "a", [Path("b")], 2)
    assert q[0][2] == "a"


def test_reconcile_queue_pop_next_respects_worker_state() -> None:
    q = [(1, "active", "x", [Path("a")])]
    out, item = queue_utils.reconcile_queue_pop_next(q, worker_running=True)
    assert item is None
    assert out == q

    out2, item2 = queue_utils.reconcile_queue_pop_next(q, worker_running=False)
    assert item2 is not None
    assert out2 == []
