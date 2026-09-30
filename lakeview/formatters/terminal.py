"""Compact Rich reports; data values are never interpreted as markup."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text


def number(value: Any) -> str:
    return "—" if value is None else f"{value:.5g}" if isinstance(value, float) else str(value)


def sparkline(bins: list[int]) -> str:
    maximum = max(bins, default=0)
    return "".join("▁▂▃▄▅▆▇█"[round(v / maximum * 7)] for v in bins) if maximum else "────────"


def render(report: dict[str, Any], console: Console) -> None:
    if "schema" in report:
        table = Table(title="lakeview · semantic diff")
        for name, color in (
            ("Added", "green"),
            ("Removed", "red"),
            ("Modified", "yellow"),
            ("Unchanged", "cyan"),
        ):
            table.add_column(name, style=color, justify="right")
        table.add_row(*(number(report[k]) for k in ("added", "removed", "modified", "unchanged")))
        console.print(table)
        schema = Table("Change", "Column", "Type", title="Schema drift")
        for kind, columns in report["schema"].items():
            for name, dtype in columns.items():
                schema.add_row(Text(kind), Text(name), Text(str(dtype)))
        if schema.row_count:
            console.print(schema)
        drift = Table(
            "Column",
            "Statistic",
            "Source",
            "Target",
            "Delta",
            title="Numerical drift · finite values",
        )
        for name, values in report["metrics"].items():
            for stat in ("mean", "variance", "min", "max"):
                drift.add_row(
                    Text(name),
                    stat,
                    *(number(values[side][stat]) for side in ("source", "target", "delta")),
                )
        if drift.row_count:
            console.print(drift)
        console.print(
            "Mode: " + report["mode"] + ". Schema changes reported separately; "
            "values compared on shared identical-type columns.",
            markup=False,
        )
    else:
        console.print(
            f"lakeview · {report['rows']:,} rows · {report['file_bytes']:,} file bytes",
            markup=False,
        )
        console.print(f"Process RSS after scan: {report['process_rss_bytes'] / 1024**2:.1f} MiB")
        table = Table(
            "Column", "Type", "Null %", "Mean", "Min / Max", "Q25 / Q50 / Q75 ≈", "Distribution"
        )
        for col in report["columns"]:
            table.add_row(
                Text(col["name"]),
                col["type"],
                f"{col['null_percent']:.2f}",
                number(col.get("mean")),
                f"{number(col.get('min'))} / {number(col.get('max'))}",
                " / ".join(number(v) for v in (col.get("quantiles") or [])),
                sparkline(col.get("histogram", [])),
            )
        console.print(table)
        console.print(
            "Counts exact · quantiles approximate · statistics exclude NaN/Infinity · "
            "file bytes are not RAM usage"
        )
    console.print(f"Completed in {report['elapsed_ms']:,.1f} ms", style="dim")
