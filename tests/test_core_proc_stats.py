from __future__ import annotations

import os

from homebase.core.proc_stats import (
    CpuSampler,
    current_rss_bytes,
    other_process_usage,
    peak_rss_bytes,
    process_cpu_s,
)


def test_cpu_sampler_percent_of_one_core() -> None:
    sampler = CpuSampler(last_cpu_s=1.0, last_wall_s=10.0)
    assert sampler.sample(cpu_s=1.5, wall_s=11.0) == 50.0
    assert sampler.sample(cpu_s=1.5, wall_s=11.0) == 0.0  # no time passed
    assert sampler.sample(cpu_s=1.4, wall_s=12.0) == 0.0  # never negative


def test_process_numbers_are_plausible() -> None:
    assert process_cpu_s() > 0
    rss = current_rss_bytes()
    assert rss is not None and rss > 1_000_000
    assert peak_rss_bytes() >= rss // 2


def test_other_process_usage() -> None:
    rss, cpu = other_process_usage(os.getpid())
    assert rss is not None and rss > 0
    assert cpu is not None and cpu >= 0
    assert other_process_usage(-1) == (None, None)
