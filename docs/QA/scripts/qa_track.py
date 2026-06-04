#!/usr/bin/env python3
"""QA tracking: run tools, record metrics, regenerate SVG charts.

Usage:
    uv run python docs/QA/scripts/qa_track.py                # all tools
    uv run python docs/QA/scripts/qa_track.py mypy bandit    # subset
    uv run python docs/QA/scripts/qa_track.py --charts-only  # only regen SVG

Tool names: mypy, coverage, import-linter, bandit, radon-cc.

CSV written to docs/QA/history/<tool>.csv, one row per date (the day's
row is replaced on re-run). SVG written to docs/QA/graphs/<tool>.svg.
Pure-stdlib — no extra dependencies.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent.parent
HISTORY = QA_DIR / "history"
GRAPHS = QA_DIR / "graphs"
REPO = QA_DIR.parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return r.stdout + r.stderr


def parse_mypy(out: str) -> dict[str, float]:
    m = re.search(r"Found (\d+) errors? in (\d+) files?", out)
    if m:
        return {"errors": int(m.group(1)), "files": int(m.group(2))}
    if "Success" in out:
        return {"errors": 0, "files": 0}
    raise ValueError("could not parse mypy output")


def parse_coverage(out: str) -> dict[str, float]:
    m = re.search(r"^TOTAL\s+.*?(\d+(?:\.\d+)?)\s*%\s*$", out, re.MULTILINE)
    if not m:
        raise ValueError("could not parse coverage output")
    return {"pct": float(m.group(1))}


def parse_import_linter(out: str) -> dict[str, float]:
    return {"violations": len(re.findall(r"^- homebase", out, re.MULTILINE))}


def parse_bandit(out: str) -> dict[str, float]:
    h = re.search(r"High:\s+(\d+)", out)
    md = re.search(r"Medium:\s+(\d+)", out)
    lo = re.search(r"Low:\s+(\d+)", out)
    if not (h and md and lo):
        raise ValueError("could not parse bandit output")
    return {"high": int(h.group(1)), "medium": int(md.group(1)), "low": int(lo.group(1))}


def parse_radon_cc(out: str) -> dict[str, float]:
    avg = re.search(r"Average complexity:\s+\w+\s+\(([\d.]+)\)", out)
    if not avg:
        raise ValueError("could not parse radon cc output")
    rank_c_plus = len(re.findall(r" - [CDEF] \(", out))
    return {"avg": float(avg.group(1)), "rank_c_plus": rank_c_plus}


def _benchmark_yaml_path() -> Path:
    import yaml as _yaml  # noqa: F401  # ensure dep present before importing pkg

    from homebase.core import utils as core_utils
    from homebase.core.constants import (
        BENCHMARK_REPORT_FILE_NAME,
        HOMEBASE_DIR_NAME,
    )

    base_dir = core_utils.resolve_base_dir(None, os.environ.get("BASE_FOLDER"))
    return base_dir / HOMEBASE_DIR_NAME / BENCHMARK_REPORT_FILE_NAME


def _benchmark_label_rows(
    runs: list[dict[str, object]],
) -> list[dict[str, str]]:
    """Sort runs, group by date, suffix `_N` when multiple per day.

    Projects `score` (composite warm+cold), `warm_sc`, and `cold_sc`.
    `score` is the weighted average from `workspace/benchmark.py` —
    `BENCHMARK_SCORE_WARM_WEIGHT * warm + BENCHMARK_SCORE_COLD_WEIGHT * cold`.
    """
    cleaned: list[tuple[str, float, float, float]] = []
    for r in runs:
        ts = r.get("timestamp")
        score = r.get("score")
        warm = r.get("score_warm")
        cold = r.get("score_cold")
        if not isinstance(ts, str):
            continue
        if not all(isinstance(v, (int, float)) for v in (score, warm, cold)):
            continue
        cleaned.append((ts, float(score), float(warm), float(cold)))  # type: ignore[arg-type]
    cleaned.sort(key=lambda x: x[0])

    by_date: dict[str, list[tuple[str, float, float, float]]] = {}
    for entry in cleaned:
        by_date.setdefault(entry[0][:10], []).append(entry)

    rows: list[dict[str, str]] = []
    for date in sorted(by_date):
        day = by_date[date]
        total = len(day)
        for i, (_ts, score, warm, cold) in enumerate(day):
            label = date if total == 1 else f"{date}_{i + 1}"
            rows.append(
                {
                    "date": label,
                    "score": _fmt(score),
                    "warm_sc": _fmt(warm),
                    "cold_sc": _fmt(cold),
                }
            )
    return rows


def record_benchmark() -> dict[str, float]:
    import yaml

    yaml_path = _benchmark_yaml_path()
    if not yaml_path.is_file():
        raise FileNotFoundError(f"benchmark report not found: {yaml_path}")
    data = yaml.safe_load(yaml_path.read_text()) or {}
    rows = _benchmark_label_rows(list(data.get("runs") or []))
    csv_path = HISTORY / "benchmark.csv"
    cols = ["date", "score", "warm_sc", "cold_sc"]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    render_chart(
        csv_path,
        GRAPHS / "benchmark.svg",
        "benchmark score",
        "score",
        y_min_mode="auto",
    )
    if not rows:
        return {"runs": 0}
    last = rows[-1]
    return {
        "runs": len(rows),
        "score": float(last["score"]),
        "warm_sc": float(last["warm_sc"]),
        "cold_sc": float(last["cold_sc"]),
    }


Spec = dict[str, object]
TOOLS: dict[str, Spec] = {
    "mypy": {
        "cmd": ["uv", "run", "mypy", "src/homebase"],
        "parse": parse_mypy,
        "title": "mypy errors",
        "ylabel": "errors",
    },
    "coverage": {
        "cmd": ["uv", "run", "pytest", "--cov=homebase", "--cov-report=term", "-q"],
        "parse": parse_coverage,
        "title": "branch coverage",
        "ylabel": "%",
    },
    "import-linter": {
        "cmd": ["uv", "run", "lint-imports"],
        "parse": parse_import_linter,
        "title": "import-linter violations",
        "ylabel": "violations",
    },
    "bandit": {
        "cmd": ["uv", "run", "bandit", "-c", "pyproject.toml", "-r", "src/homebase"],
        "parse": parse_bandit,
        "title": "bandit findings",
        "ylabel": "count",
    },
    "radon-cc": {
        "cmd": ["uv", "run", "radon", "cc", "src/homebase", "-a", "-s", "-n", "C"],
        "parse": parse_radon_cc,
        "title": "radon cyclomatic complexity",
        "ylabel": "value",
    },
    "benchmark": {
        "record": record_benchmark,
        "title": "benchmark score",
        "ylabel": "score",
        "y_min_mode": "auto",
    },
}


def append_csv(name: str, metrics: dict[str, float]) -> Path:
    today = dt.date.today().isoformat()
    csv_path = HISTORY / f"{name}.csv"
    cols = ["date"] + list(metrics.keys())
    rows: list[dict[str, str]] = []
    if csv_path.exists():
        with csv_path.open() as f:
            rows = list(csv.DictReader(f))
    rows = [r for r in rows if r.get("date") != today]
    rows.append({"date": today, **{k: _fmt(v) for k, v in metrics.items()}})
    rows.sort(key=lambda r: r["date"])
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return csv_path


def _fmt(v: float) -> str:
    return f"{v:.2f}" if isinstance(v, float) and not v.is_integer() else str(int(v))


def render_chart(
    csv_path: Path,
    out_path: Path,
    title: str,
    ylabel: str,
    *,
    y_min_mode: str = "zero",
) -> None:
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    series_keys = [k for k in rows[0].keys() if k != "date"]
    series = {k: [float(r[k]) for r in rows] for k in series_keys}
    n = len(rows)

    W, H = 720, 320
    pad_l, pad_r, pad_t, pad_b = 60, 140, 32, 50
    plot_w, plot_h = W - pad_l - pad_r, H - pad_t - pad_b

    all_vals = [v for vs in series.values() for v in vs]
    y_max = max(all_vals) if all_vals else 1.0
    data_min = min(all_vals) if all_vals else 0.0
    if y_min_mode == "auto":
        span = max(y_max - data_min, 1.0)
        y_min = data_min - span * 0.05
        y_max = y_max + span * 0.05
    else:
        y_min = min(data_min, 0.0)
    if y_max == y_min:
        y_max = y_min + 1.0
    y_span = y_max - y_min

    def x_at(i: int) -> float:
        if n == 1:
            return pad_l + plot_w / 2
        return pad_l + i / (n - 1) * plot_w

    def y_at(v: float) -> float:
        return pad_t + plot_h - (v - y_min) / y_span * plot_h

    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e"]
    p: list[str] = []
    p.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'font-family="monospace" font-size="11">'
    )
    p.append('<rect width="100%" height="100%" fill="white"/>')
    p.append(
        f'<text x="{W // 2}" y="20" text-anchor="middle" '
        f'font-weight="bold" font-size="13">{title}</text>'
    )
    # gridlines + y ticks
    for i in range(5):
        v = y_min + y_span * i / 4
        y = y_at(v)
        p.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" '
            f'stroke="#eee"/>'
        )
        p.append(
            f'<text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end" '
            f'fill="#555">{v:.1f}</text>'
        )
    # axes
    p.append(
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + plot_h}" '
        f'stroke="#888"/>'
    )
    p.append(
        f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{pad_l + plot_w}" '
        f'y2="{pad_t + plot_h}" stroke="#888"/>'
    )
    # x labels (first, middle, last)
    idxs = sorted({0, n // 2, n - 1})
    for i in idxs:
        x = x_at(i)
        p.append(
            f'<line x1="{x:.1f}" y1="{pad_t + plot_h}" x2="{x:.1f}" '
            f'y2="{pad_t + plot_h + 4}" stroke="#888"/>'
        )
        p.append(
            f'<text x="{x:.1f}" y="{pad_t + plot_h + 18}" text-anchor="middle" '
            f'fill="#555">{rows[i]["date"]}</text>'
        )
    p.append(
        f'<text x="14" y="{pad_t + plot_h // 2}" text-anchor="middle" '
        f'transform="rotate(-90 14 {pad_t + plot_h // 2})" fill="#555">{ylabel}</text>'
    )
    # series
    for idx, (k, vals) in enumerate(series.items()):
        color = colors[idx % len(colors)]
        if n > 1:
            d = " ".join(
                ("M" if i == 0 else "L") + f"{x_at(i):.1f},{y_at(v):.1f}"
                for i, v in enumerate(vals)
            )
            p.append(
                f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"/>'
            )
        for i, v in enumerate(vals):
            p.append(
                f'<circle cx="{x_at(i):.1f}" cy="{y_at(v):.1f}" r="3" '
                f'fill="{color}"/>'
            )
        ly = pad_t + 20 + idx * 18
        p.append(
            f'<rect x="{W - pad_r + 8}" y="{ly - 10}" width="12" height="12" '
            f'fill="{color}"/>'
        )
        last = vals[-1]
        p.append(
            f'<text x="{W - pad_r + 24}" y="{ly}" fill="#222">{k}: '
            f'{last:g}</text>'
        )
    p.append("</svg>")
    out_path.write_text("\n".join(p) + "\n")


def record(name: str) -> dict[str, float]:
    spec = TOOLS[name]
    if "record" in spec:
        custom: Callable[[], dict[str, float]] = spec["record"]  # type: ignore[assignment]
        return custom()
    cmd = spec["cmd"]  # type: ignore[index]
    parser: Callable[[str], dict[str, float]] = spec["parse"]  # type: ignore[assignment]
    out = run(cmd)  # type: ignore[arg-type]
    metrics = parser(out)
    csv_path = append_csv(name, metrics)
    render_chart(
        csv_path,
        GRAPHS / f"{name}.svg",
        spec["title"],  # type: ignore[arg-type]
        spec["ylabel"],  # type: ignore[arg-type]
        y_min_mode=str(spec.get("y_min_mode", "zero")),
    )
    return metrics


def main(argv: list[str] | None = None) -> int:
    HISTORY.mkdir(exist_ok=True)
    GRAPHS.mkdir(exist_ok=True)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("tools", nargs="*", help="tool name(s); default = all")
    p.add_argument(
        "--charts-only",
        action="store_true",
        help="regenerate SVG from existing CSV without running tools",
    )
    args = p.parse_args(argv)
    names = args.tools or list(TOOLS)
    unknown = set(names) - set(TOOLS)
    if unknown:
        print(f"unknown tools: {sorted(unknown)}", file=sys.stderr)
        return 2
    for name in names:
        if args.charts_only:
            csv_path = HISTORY / f"{name}.csv"
            if not csv_path.exists():
                print(f"{name}: no history yet", file=sys.stderr)
                continue
            spec = TOOLS[name]
            render_chart(
                csv_path,
                GRAPHS / f"{name}.svg",
                spec["title"],  # type: ignore[arg-type]
                spec["ylabel"],  # type: ignore[arg-type]
                y_min_mode=str(spec.get("y_min_mode", "zero")),
            )
            print(f"{name}: chart regenerated")
        else:
            metrics = record(name)
            print(f"{name}: {metrics}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
