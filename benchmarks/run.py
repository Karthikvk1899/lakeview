"""Reproducible subprocess benchmark; no performance claims without measurements.

Run: uv run --extra benchmark python benchmarks/run.py --rows 1000000
Outputs JSON with all samples, medians, and process-tree peak RSS observations.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from importlib.metadata import version
from pathlib import Path

import duckdb
import psutil

parser = argparse.ArgumentParser()
parser.add_argument("--rows", type=int, default=1_000_000)
parser.add_argument("--repeats", type=int, default=3)
args = parser.parse_args()
if args.rows < 1 or args.repeats < 1:
    parser.error("rows and repeats must be positive")


def measure(command: list[str]) -> dict[str, float]:
    start = time.perf_counter()
    peak = 0
    with tempfile.TemporaryFile() as stderr:
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=stderr)
        root = psutil.Process(proc.pid)
        while proc.poll() is None:
            try:
                peak = max(
                    peak, sum(p.memory_info().rss for p in [root, *root.children(recursive=True)])
                )
            except psutil.Error:
                pass
            time.sleep(0.01)
        if proc.returncode:
            stderr.seek(0)
            raise RuntimeError(stderr.read().decode(errors="replace"))
    return {
        "wall_ms": round((time.perf_counter() - start) * 1000, 2),
        "peak_rss_mib": round(peak / 1024**2, 2),
    }


with tempfile.TemporaryDirectory(prefix="lakeview-bench-") as folder:
    file = Path(folder) / "data.parquet"
    with duckdb.connect() as con:
        con.execute(
            "COPY (SELECT i id, CASE WHEN i % 17 = 0 THEN NULL ELSE "
            "sin(i)*100 END AS metric, 'group-' || (i % 100) category "
            f"FROM range({args.rows}) t(i)) TO '{file.as_posix()}' (FORMAT PARQUET)"
        )
    tasks = {
        "lakeview_help": [sys.executable, "-m", "lakeview", "--help"],
        "pandas_import": [sys.executable, "-c", "import pandas"],
        "lakeview_profile": [
            sys.executable,
            "-m",
            "lakeview",
            "profile",
            str(file),
            "--format",
            "json",
        ],
        "pandas_describe": [
            sys.executable,
            "-c",
            "import pandas as pd,sys; d=pd.read_parquet(sys.argv[1]); "
            "d.describe(include='all'); d.isna().sum()",
            str(file),
        ],
    }
    output = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_logical": psutil.cpu_count(),
        "rows": args.rows,
        "file_bytes": file.stat().st_size,
        "versions": {p: version(p) for p in ("duckdb", "pyarrow", "pandas", "lakeview-cli")},
        "notes": "Fresh processes; warm OS cache possible; peak RSS sampled every 10 ms. "
        "describe is not feature-equivalent to lakeview. Spark not measured.",
        "results": {},
    }
    for name, command in tasks.items():
        samples = [measure(command) for _ in range(args.repeats)]
        output["results"][name] = {
            "samples": samples,
            "median_ms": statistics.median(s["wall_ms"] for s in samples),
            "median_peak_rss_mib": statistics.median(s["peak_rss_mib"] for s in samples),
        }
    print(json.dumps(output, indent=2))
