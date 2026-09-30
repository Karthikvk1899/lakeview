"""Exact bag comparisons and null-safe, unique-key row comparisons."""

from __future__ import annotations

import time
from typing import Any

from lakeview.core.engine import Engine, LakeviewError, ident, numeric


def metrics(engine: Engine, table: str, columns: list[str]) -> dict[str, dict[str, Any]]:
    if not columns:
        return {}
    expressions: list[str] = []
    scales = engine.scales(table, columns)
    for name in columns:
        value = f"CASE WHEN isfinite({ident(name)}::DOUBLE) THEN {ident(name)}::DOUBLE END"
        scale = scales[name]
        expressions.extend(
            [
                f"avg(({value})/{scale!r})*{scale!r}",
                f"var_pop(({value})/{scale!r})*{scale!r}*{scale!r}",
                f"min({value})",
                f"max({value})",
            ]
        )
    row = engine.con.execute(f"SELECT {', '.join(expressions)} FROM {ident(table)}").fetchone()
    assert row is not None
    return {
        name: dict(zip(("mean", "variance", "min", "max"), row[i * 4 : i * 4 + 4], strict=True))
        for i, name in enumerate(columns)
    }


def diff(engine: Engine, source: str, target: str, keys: list[str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    engine.load(source, "src")
    engine.load(target, "dst")
    left, right = engine.schema("src"), engine.schema("dst")
    common = [name for name in left if name in right]
    added_columns = {name: right[name] for name in right if name not in left}
    removed_columns = {name: left[name] for name in left if name not in right}
    changed_types = {
        name: {"source": left[name], "target": right[name]}
        for name in common
        if left[name] != right[name]
    }
    counts = {
        table: int(engine.scalar(f"SELECT count(*) FROM {table}")) for table in ("src", "dst")
    }
    comparable = [name for name in common if left[name] == right[name]]
    unchanged = 0
    modified: int | None = None
    if keys:
        if len(keys) != len(set(keys)):
            raise LakeviewError("Join keys must not be repeated.")
        for key in keys:
            if key not in comparable:
                raise LakeviewError(f"Key {key!r} must exist on both sides with identical types.")
        key_sql = ", ".join(ident(k) for k in keys)
        for table in ("src", "dst"):
            if engine.scalar(
                f"SELECT EXISTS (SELECT 1 FROM {table} GROUP BY {key_sql} HAVING count(*) > 1)"
            ):
                raise LakeviewError(
                    f"Duplicate keys in {table}; use unique keys or omit --on for bag comparison."
                )
        join = " AND ".join(f"s.{ident(k)} IS NOT DISTINCT FROM t.{ident(k)}" for k in keys)
        shared_values = [name for name in comparable if name not in keys]
        changes = (
            " OR ".join(f"s.{ident(c)} IS DISTINCT FROM t.{ident(c)}" for c in shared_values)
            or "false"
        )
        matched, modified_raw = engine.con.execute(
            f"SELECT count(*), count(*) FILTER (WHERE {changes}) FROM src s JOIN dst t ON {join}"
        ).fetchone() or (0, 0)
        modified = int(modified_raw)
        unchanged = int(matched) - modified
        added, removed = counts["dst"] - int(matched), counts["src"] - int(matched)
    else:
        if set(left) != set(right) or changed_types:
            added, removed = counts["dst"], counts["src"]
        else:
            cols = ", ".join(ident(c) for c in left)
            removed = int(
                engine.scalar(
                    f"SELECT count(*) FROM (SELECT {cols} FROM src "
                    f"EXCEPT ALL SELECT {cols} FROM dst)"
                )
            )
            added = int(
                engine.scalar(
                    f"SELECT count(*) FROM (SELECT {cols} FROM dst "
                    f"EXCEPT ALL SELECT {cols} FROM src)"
                )
            )
            unchanged = counts["src"] - removed
    metric_names = [name for name in common if numeric(left[name]) and numeric(right[name])]
    source_metrics, target_metrics = (
        metrics(engine, "src", metric_names),
        metrics(engine, "dst", metric_names),
    )
    drift = {
        name: {
            "source": source_metrics[name],
            "target": target_metrics[name],
            "delta": {
                stat: (
                    target_metrics[name][stat] - source_metrics[name][stat]
                    if source_metrics[name][stat] is not None
                    and target_metrics[name][stat] is not None
                    else None
                )
                for stat in source_metrics[name]
            },
        }
        for name in metric_names
    }
    schema_changed = bool(added_columns or removed_columns or changed_types)
    return {
        "source": source,
        "target": target,
        "mode": "keyed" if keys else "multiset",
        "keys": keys or [],
        "source_rows": counts["src"],
        "target_rows": counts["dst"],
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged,
        "schema": {"added": added_columns, "removed": removed_columns, "changed": changed_types},
        "compared_columns": comparable if keys else list(left),
        "metrics": drift,
        "different": schema_changed or bool(added or removed or modified),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
