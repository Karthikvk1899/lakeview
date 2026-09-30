import json
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from lakeview.cli import app
from lakeview.formatters.markdown import cell

runner = CliRunner()


@pytest.mark.parametrize(
    "command",
    [["--help"], ["profile", "--help"], ["diff", "--help"], ["query", "--help"], ["--version"]],
)
def test_help(command):
    result = runner.invoke(app, command)
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("fmt", ["terminal", "json", "markdown"])
def test_profile(datasets, fmt):
    path = datasets("a", {"id": [1, 2]})
    result = runner.invoke(app, ["profile", path, "--format", fmt])
    assert result.exit_code == 0, result.output
    if fmt == "json":
        assert json.loads(result.stdout)["rows"] == 2


def test_diff_exit_codes(datasets):
    a, b = datasets("a", {"id": [1]}), datasets("b", {"id": [2]})
    result = runner.invoke(app, ["diff", a, b, "--format", "json", "--fail-on-change"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["different"]
    assert runner.invoke(app, ["diff", a, a, "--fail-on-change"]).exit_code == 0


@pytest.mark.parametrize(
    "filename", ["missing.parquet", "bad.parquet", "bad.csv", "bad.txt", "bad.arrow"]
)
def test_bad_files(tmp_path, filename):
    path = tmp_path / filename
    if filename != "missing.parquet":
        path.write_bytes(b"\x00\xffnot data")
    result = runner.invoke(app, ["profile", str(path)])
    assert result.exit_code == 2, result.output
    assert "Traceback" not in result.output


def test_query(datasets):
    path = datasets("a", {"id": [1, 2]})
    result = runner.invoke(app, ["query", "SELECT sum(id) n FROM data", path, "--format", "jsonl"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"n": "3"}  # HUGEINT is Arrow decimal128.


def test_query_truncation():
    result = runner.invoke(app, ["query", "SELECT * FROM range(1000)", "--limit", "2"])
    assert result.exit_code == 0
    assert "truncated" in result.output


def test_sql_error():
    result = runner.invoke(app, ["query", "SELECT * FROM nope"])
    assert result.exit_code == 2
    assert "Traceback" not in result.output


def test_markdown_escape():
    assert cell("<script>|\n`") == "&lt;script&gt;&#124; &#96;"


def test_subprocess_help():
    result = subprocess.run(
        [sys.executable, "-m", "lakeview", "--help"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


@pytest.mark.parametrize("fmt", ["terminal", "markdown"])
def test_schema_report(datasets, fmt):
    a = datasets("a", {"id": [1], "v": [1]})
    b = datasets("b", {"id": [1], "v": [2], "extra": [True]})
    result = runner.invoke(app, ["diff", a, b, "--on", "id", "--format", fmt])
    assert result.exit_code == 0, result.output
    assert "extra" in result.output


def test_nonfinite_json(datasets):
    path = datasets("a", {"v": [-1e308, 1e308]})
    result = runner.invoke(app, ["profile", path, "--format", "json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["columns"][0]["variance"] is None
