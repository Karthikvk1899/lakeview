from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from lakeview.core.engine import Engine, LakeviewError
from lakeview.core.profiler import profile


@pytest.mark.parametrize("stream", [False, True])
def test_ipc(engine, tmp_path, stream):
    table = pa.table({"id": [1, 2, 3], "value": [1.0, None, 3.0]})
    path = tmp_path / "data.arrow"
    with pa.OSFile(str(path), "wb") as sink:
        with (ipc.new_stream if stream else ipc.new_file)(sink, table.schema) as writer:
            for batch in table.to_batches(max_chunksize=1):
                writer.write_batch(batch)
    report = profile(engine, str(path))
    assert report["rows"] == 3
    assert sum(report["columns"][0]["histogram"]) == 3


def test_database_readonly(engine, tmp_path):
    path = tmp_path / "data.duckdb"
    with duckdb.connect(str(path)) as db:
        db.execute("CREATE TABLE example AS SELECT 1 id")
    original = path.read_bytes()
    assert profile(engine, str(path))["rows"] == 1
    assert path.read_bytes() == original


def test_database_selector(engine, tmp_path):
    path = tmp_path / "data.duckdb"
    with duckdb.connect(str(path)) as db:
        db.execute("CREATE TABLE a AS SELECT 1 id; CREATE TABLE b AS SELECT 2 id")
    assert profile(engine, str(path) + "::b")["columns"][0]["mean"] == 2


def test_same_database_diff(engine, tmp_path):
    from lakeview.core.differ import diff

    path = tmp_path / "same.duckdb"
    with duckdb.connect(str(path)) as db:
        db.execute("CREATE TABLE a AS SELECT 1 id; CREATE TABLE b AS SELECT 2 id")
    assert diff(engine, str(path) + "::a", str(path) + "::b")["added"] == 1


def test_ambiguous_database(engine, tmp_path):
    path = tmp_path / "data.duckdb"
    with duckdb.connect(str(path)) as db:
        db.execute("CREATE TABLE a(i INT); CREATE TABLE b(i INT)")
    with pytest.raises(LakeviewError, match="Choose one table"):
        engine.load(str(path), "data")


@pytest.mark.parametrize("suffix,delimiter", [("csv", ","), ("tsv", "\t")])
def test_delimited(engine, tmp_path, suffix, delimiter):
    path = tmp_path / f"a.{suffix}"
    path.write_text(f"id{delimiter}v\n1{delimiter}2\n2{delimiter}\n")
    assert profile(engine, str(path))["columns"][1]["null_percent"] == 50


@pytest.mark.parametrize(
    "sql", ["CREATE TABLE x(a INT)", "SELECT 1; SELECT 2", "COPY (SELECT 1) TO 'x.csv'"]
)
def test_query_rejects_non_select(engine, sql):
    with pytest.raises(LakeviewError):
        list(engine.query(sql))


def test_batch_stream(engine):
    batches = list(engine.query("SELECT * FROM range(20000)", 1024))
    assert sum(map(len, batches)) == 20000
    assert max(map(len, batches)) == 1024


def test_cleanup():
    with Engine() as engine:
        temp = Path(engine.temp.name)
        assert temp.is_dir()
    assert not temp.exists()


@pytest.mark.parametrize("memory,threads", [("wat", 4), ("512MB", 0)])
def test_bad_config(memory, threads):
    with pytest.raises(LakeviewError):
        Engine(memory, threads)
