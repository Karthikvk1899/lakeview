"""Portable reports with escaped data-controlled Markdown cells."""

from __future__ import annotations

import html
import math
from typing import Any


def clean(value: Any) -> Any:
    """Convert non-finite results to JSON null, recursively."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def cell(value: Any) -> str:
    text = "—" if value is None else str(value)
    return (
        html.escape(text)
        .replace("|", "&#124;")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("`", "&#96;")
    )


def markdown(report: dict[str, Any]) -> str:
    if "schema" in report:
        lines = [
            "## lakeview data diff",
            "",
            "| Added | Removed | Modified | Unchanged |",
            "| ---: | ---: | ---: | ---: |",
            "| "
            + " | ".join(cell(report[k]) for k in ("added", "removed", "modified", "unchanged"))
            + " |",
            "",
            f"Mode: {report['mode']}. Modified is unavailable in multiset mode.",
            "",
            "### Schema drift",
            "",
            "| Change | Column | Type |",
            "| --- | --- | --- |",
        ]
        for kind, columns in report["schema"].items():
            for name, dtype in columns.items():
                lines.append(f"| {cell(kind)} | {cell(name)} | {cell(dtype)} |")
        lines.extend(
            [
                "",
                "### Numerical drift (finite values)",
                "",
                "| Column | Statistic | Source | Target | Delta |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for name, values in report["metrics"].items():
            for stat in ("mean", "variance", "min", "max"):
                lines.append(
                    "| "
                    + " | ".join(
                        cell(v)
                        for v in (
                            name,
                            stat,
                            values["source"][stat],
                            values["target"][stat],
                            values["delta"][stat],
                        )
                    )
                    + " |"
                )
        lines.extend(
            [
                "",
                "Row comparisons use shared columns with identical types; "
                "schema changes are separate.",
            ]
        )
    else:
        lines = [
            "## lakeview profile",
            "",
            f"Rows: {report['rows']:,}. File bytes: {report['file_bytes']:,}.",
            "",
            "| Column | Type | Null % | Mean | Min | Max | Approx. Q25/Q50/Q75 |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for col in report["columns"]:
            lines.append(
                "| "
                + " | ".join(
                    cell(col.get(k))
                    for k in ("name", "type", "null_percent", "mean", "min", "max", "quantiles")
                )
                + " |"
            )
    return "\n".join(lines) + "\n"
