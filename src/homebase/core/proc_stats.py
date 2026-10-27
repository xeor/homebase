"""CPU and memory of this process, without third-party packages."""
from __future__ import annotations

import os
import resource
import subprocess
import sys
import time
from dataclasses import dataclass, field


def process_cpu_s() -> float:
    """User + system CPU seconds of this process (all threads)."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def peak_rss_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes, Linux KiB.
    return int(peak) if sys.platform == "darwin" else int(peak) * 1024


def current_rss_bytes(pid: int | None = None) -> int | None:
    """Resident memory now; None when it cannot be read."""
    target = os.getpid() if pid is None else pid
    try:
        with open(f"/proc/{target}/statm", encoding="ascii") as handle:
            return int(handle.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        pass
    try:
        proc = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(target)],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        return int(proc.stdout.strip()) * 1024
    except ValueError:
        return None


@dataclass
class CpuSampler:
    """CPU use since the previous sample, in percent of one core."""

    last_cpu_s: float = field(default_factory=process_cpu_s)
    last_wall_s: float = field(default_factory=time.monotonic)

    def sample(self, cpu_s: float | None = None, wall_s: float | None = None) -> float:
        cpu = process_cpu_s() if cpu_s is None else cpu_s
        wall = time.monotonic() if wall_s is None else wall_s
        elapsed = wall - self.last_wall_s
        used = cpu - self.last_cpu_s
        self.last_cpu_s = cpu
        self.last_wall_s = wall
        if elapsed <= 0:
            return 0.0
        return max(0.0, used / elapsed * 100.0)


def other_process_usage(pid: int) -> tuple[int | None, float | None]:
    """(resident bytes, CPU percent as ps reports it) of another process."""
    try:
        proc = subprocess.run(
            ["ps", "-o", "rss=,%cpu=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None
    parts = proc.stdout.split()
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]) * 1024, float(parts[1].replace(",", "."))
    except ValueError:
        return None, None
