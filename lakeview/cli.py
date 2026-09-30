"""Terminal entry points and stable automation exit codes."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import StrEnum
from io import TextIOWrapper
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from lakeview import __version__
from lakeview.formatters.markdown import clean, markdown
from lakeview.formatters.terminal import render

if TYPE_CHECKING:
    from lakeview.core.engine import Engine

# Windows redirected streams may default to cp1252; reports are UTF-8.
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Local data profiling, exact diffs, and streaming SQL.",
)
console = Console(highlight=False)
errors = Console(stderr=True, highlight=False)


class Format(StrEnum):
    terminal = "terminal"
    json = "json"
    markdown = "markdown"


class QueryFormat(StrEnum):
    terminal = "terminal"
    jsonl = "jsonl"


@contextmanager
def guarded() -> Iterator[None]:
    import duckdb
    import pyarrow as pa

    from lakeview.core.engine import LakeviewError

    try:
        yield
    except (LakeviewError, duckdb.Error, pa.ArrowException, OSError, ValueError) as exc:
        errors.print(Text(f"Error: {exc}", style="red"))
        raise typer.Exit(2) from None


def output(
    run: Callable[[Engine], dict[str, Any]], fmt: Format, memory_limit: str, threads: int
) -> dict[str, Any]:
    from lakeview.core.engine import Engine

    with guarded(), Engine(memory_limit, threads) as engine:
        with errors.status("Scanning local data…") if errors.is_terminal else _quiet():
            report = clean(run(engine))
        if fmt == Format.json:
            typer.echo(json.dumps(report, ensure_ascii=True, allow_nan=False, default=str))
        elif fmt == Format.markdown:
            typer.echo(markdown(report), nl=False)
        else:
            render(report, console)
        return dict(report)


@contextmanager
def _quiet() -> Iterator[None]:
    yield


def version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version_flag: Annotated[
        bool, typer.Option("--version", callback=version, is_eager=True)
    ] = False,
) -> None:
    """Inspect local data with DuckDB. No service, account, or warehouse."""


@app.command()
def profile(
    file: str, format: Format = Format.terminal, memory_limit: str = "512MB", threads: int = 4
) -> None:
    """Profile a file (or database.duckdb::schema.table)."""
    from lakeview.core.profiler import profile as summarize

    output(lambda e: summarize(e, file), format, memory_limit, threads)


@app.command()
def diff(
    source: str,
    target: str,
    on: Annotated[
        str | None, typer.Option(help="Comma-separated unique keys; NULL matches NULL.")
    ] = None,
    format: Format = Format.terminal,
    fail_on_change: bool = False,
    memory_limit: str = "512MB",
    threads: int = 4,
) -> None:
    """Compare source → target; --fail-on-change returns 1 for differences, 2 for errors."""
    from lakeview.core.differ import diff as compare

    keys = [k.strip() for k in on.split(",")] if on is not None else None
    report = output(lambda e: compare(e, source, target, keys), format, memory_limit, threads)
    if fail_on_change and report["different"]:
        raise typer.Exit(1)


@app.command()
def query(
    sql: str,
    files: Annotated[list[str] | None, typer.Argument()] = None,
    format: QueryFormat = QueryFormat.terminal,
    limit: Annotated[
        int, typer.Option(min=1, help="Terminal display limit; JSONL streams all rows.")
    ] = 100,
    memory_limit: str = "512MB",
    threads: int = 4,
) -> None:
    """Run one SELECT. File aliases: f1, f2, …; data aliases f1. JSONL streams all rows."""
    from lakeview.core.engine import Engine

    with guarded(), Engine(memory_limit, threads) as engine:
        for i, spec in enumerate(files or [], 1):
            engine.load(spec, f"f{i}")
        if files:
            engine.con.execute("CREATE VIEW data AS SELECT * FROM f1")
        if format == QueryFormat.jsonl:
            for batch in engine.query(sql):
                for row in batch:
                    typer.echo(
                        json.dumps(clean(row), allow_nan=False, ensure_ascii=True, default=str)
                    )
        else:
            rows: list[dict[str, Any]] = []
            for batch in engine.query(sql, min(limit + 1, 8192)):
                rows.extend(batch[: limit + 1 - len(rows)])
                if len(rows) > limit:
                    break
            table = Table(title="lakeview · query")
            if rows:
                for name in rows[0]:
                    table.add_column(Text(name))
                for row in rows[:limit]:
                    table.add_row(*(Text(str(value)) for value in row.values()))
                console.print(table)
            console.print(
                f"{min(len(rows), limit)} rows shown"
                + (" (truncated; use --format jsonl for all rows)" if len(rows) > limit else "")
            )
