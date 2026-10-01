"""Bounded DuckDB execution over local, read-only input datasets."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import TracebackType
from typing import Any

import duckdb


class LakeviewError(Exception):
    """An actionable user-facing error."""


def ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def numeric(dtype: str) -> bool:
    return bool(
        re.match(r"^(U?(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT)|FLOAT|DOUBLE|DECIMAL)", dtype)
    )


class Engine(AbstractContextManager["Engine"]):
    """Ephemeral database with disk spill; memory_limit is not a total RSS cap."""

    def __init__(self, memory_limit: str = "512MB", threads: int = 4) -> None:
        if not re.fullmatch(r"[1-9][0-9]*(?:\.[0-9]+)?(?:KB|MB|GB|TB)", memory_limit.upper()):
            raise LakeviewError("Memory limit must look like 512MB or 2GB.")
        if threads < 1:
            raise LakeviewError("Threads must be positive.")
        self.temp = TemporaryDirectory(prefix="lakeview-")
        self.resources: list[Any] = []
        self.databases: dict[Path, str] = {}
        try:
            self.con = duckdb.connect(
                ":memory:",
                config={
                    "memory_limit": memory_limit,
                    "threads": threads,
                    "temp_directory": self.temp.name,
                    "preserve_insertion_order": False,
                    "autoinstall_known_extensions": False,
                    "autoload_known_extensions": False,
                },
            )
        except Exception:
            self.temp.cleanup()
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.con.close()
        for resource in reversed(self.resources):
            resource.close()
        self.temp.cleanup()

    def scalar(self, sql: str) -> Any:
        row = self.con.execute(sql).fetchone()
        if row is None:
            raise LakeviewError("Query did not return a result.")
        return row[0]

    def schema(self, alias: str) -> dict[str, str]:
        return {
            str(row[0]): str(row[1])
            for row in self.con.execute(f"DESCRIBE {ident(alias)}").fetchall()
        }

    def scales(self, alias: str, columns: list[str]) -> dict[str, float]:
        """Finite magnitudes for stable aggregation without intermediate overflow."""
        if not columns:
            return {}
        expressions = [
            f"max(abs({ident(c)}::DOUBLE)) FILTER (WHERE isfinite({ident(c)}::DOUBLE))"
            for c in columns
        ]
        row = self.con.execute(f"SELECT {', '.join(expressions)} FROM {ident(alias)}").fetchone()
        assert row is not None
        return {c: float(v) if v else 1.0 for c, v in zip(columns, row, strict=True)}

    def load(self, spec: str, alias: str) -> Path:
        raw, sep, table = spec.partition("::")
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise LakeviewError(f"File not found: {path}")
        suffix = path.suffix.lower()
        quoted = literal(str(path))
        if suffix in {".duckdb", ".db"}:
            database = self.databases.get(path, f"db_{alias}")
            if path not in self.databases:
                self.con.execute(f"ATTACH {quoted} AS {ident(database)} (READ_ONLY)")
                self.databases[path] = database
            tables = self.con.execute(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_catalog = ? AND table_type = 'BASE TABLE' ORDER BY 1, 2",
                [database],
            ).fetchall()
            if sep:
                matches = [(s, t) for s, t in tables if table in (t, f"{s}.{t}")]
            else:
                matches = tables
            if len(matches) != 1:
                available = ", ".join(f"{s}.{t}" for s, t in tables)
                raise LakeviewError(
                    f"Choose one table with file.duckdb::schema.table. Available: {available}"
                )
            schema, name = matches[0]
            source = f"{ident(database)}.{ident(schema)}.{ident(name)}"
        elif sep:
            raise LakeviewError("The ::table selector is only supported for DuckDB files.")
        elif suffix in {".parquet", ".pq"}:
            source = f"read_parquet({quoted})"
        elif suffix in {".csv", ".tsv"}:
            delimiter = "\t" if suffix == ".tsv" else ","
            source = f"read_csv({quoted}, header=true, delim={literal(delimiter)}, sample_size=-1)"
        elif suffix in {".arrow", ".ipc", ".feather"}:
            import pyarrow as pa
            import pyarrow.dataset as ds
            import pyarrow.ipc as ipc

            handle = pa.memory_map(str(path), "r")
            self.resources.append(handle)
            try:
                ipc.open_file(handle)
            except pa.ArrowInvalid:
                import pyarrow.parquet as pq

                handle.seek(0)
                reader = ipc.open_stream(handle)
                converted = Path(self.temp.name) / f"{alias}.parquet"
                with pq.ParquetWriter(str(converted), reader.schema) as writer:
                    for batch in reader:
                        writer.write_batch(batch)
                source = f"read_parquet({literal(str(converted))})"
            else:
                self.con.register(f"arrow_{alias}", ds.dataset(str(path), format="ipc"))
                source = ident(f"arrow_{alias}")
        else:
            raise LakeviewError(
                f"Unsupported file extension: {suffix}. Use Parquet, CSV, TSV, DuckDB, or IPC."
            )
        self.con.execute(f"CREATE VIEW {ident(alias)} AS SELECT * FROM {source}")
        return path

    def query(self, sql: str, batch_size: int = 8192) -> Iterator[list[dict[str, Any]]]:
        statements = self.con.extract_statements(sql)
        if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
            raise LakeviewError("query accepts exactly one SELECT (including WITH).")
        reader = self.con.execute(sql).to_arrow_reader(batch_size)
        for batch in reader:
            yield batch.to_pylist()
