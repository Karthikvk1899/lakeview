"""Exact counts and finite-value statistics, with approximate quantiles."""

from __future__ import annotations

import time
from typing import Any

import psutil

from lakeview.core.engine import Engine, ident, numeric


def profile(engine: Engine, spec: str) -> dict[str, Any]:
    started = time.perf_counter()
    path = engine.load(spec, "data")
    schema = engine.schema("data")
    scales = engine.scales("data", [c for c, dtype in schema.items() if numeric(dtype)])
    expressions = ["count(*)"]
    for name, dtype in schema.items():
        col = ident(name)
        expressions.append(f"count(*) - count({col})")
        if numeric(dtype):
            value = f"CASE WHEN isfinite({col}::DOUBLE) THEN {col}::DOUBLE END"
            scale = scales[name]
            expressions.extend(
                [
                    f"count({col}) - count({value})",
                    f"avg(({value})/{scale!r})*{scale!r}",
                    f"var_pop(({value})/{scale!r})*{scale!r}*{scale!r}",
                    f"min({value})",
                    f"max({value})",
                    f"approx_quantile({value}, [0.25, 0.5, 0.75])",
                ]
            )
    row = engine.con.execute("SELECT " + ", ".join(expressions) + " FROM data").fetchone()
    assert row is not None
    count, cursor = int(row[0]), 1
    columns: list[dict[str, Any]] = []
    histograms: list[str] = []
    histogram_columns: list[dict[str, Any]] = []
    for name, dtype in schema.items():
        nulls = int(row[cursor])
        cursor += 1
        column: dict[str, Any] = {
            "name": name,
            "type": dtype,
            "nulls": nulls,
            "null_percent": 100 * nulls / count if count else 0.0,
        }
        if numeric(dtype):
            for field in ("nonfinite", "mean", "variance", "min", "max", "quantiles"):
                column[field] = row[cursor]
                cursor += 1
            low, high = column["min"], column["max"]
            column["histogram"] = [0] * 8
            if low is not None:
                col = f"{ident(name)}::DOUBLE"
                if high == low:
                    bucket = "0"
                else:
                    scale = max(abs(low), abs(high), 1.0)
                    bucket = (
                        f"least(7, greatest(0, floor((({col}/{scale!r}) - "
                        f"({low!r}/{scale!r})) / "
                        f"(({high!r}/{scale!r}) - ({low!r}/{scale!r})) * 8)))"
                    )
                histograms.append(
                    f"histogram(CAST(({bucket}) AS INTEGER)) FILTER (WHERE isfinite({col}))"
                )
                histogram_columns.append(column)
        columns.append(column)
    if histograms:
        bins = engine.con.execute("SELECT " + ", ".join(histograms) + " FROM data").fetchone()
        assert bins is not None
        for index, column in enumerate(histogram_columns):
            counts = bins[index] or {}
            column["histogram"] = [counts.get(bucket, 0) for bucket in range(8)]
    return {
        "file": str(path),
        "rows": count,
        "file_bytes": path.stat().st_size,
        "process_rss_bytes": psutil.Process().memory_info().rss,
        "columns": columns,
        "quantiles": "approximate",
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
