import math

import pyarrow as pa
import pytest

from lakeview.core.profiler import profile


def test_statistics(engine, datasets):
    report = profile(
        engine, datasets("stats", {"x": [1.0, 2.0, 3.0, None], "label": ["a", "b", None, "d"]})
    )
    col = report["columns"][0]
    assert report["rows"] == 4
    assert col["null_percent"] == 25
    assert col["mean"] == 2
    assert col["variance"] == pytest.approx(2 / 3)
    assert col["min"] == 1 and col["max"] == 3
    assert col["quantiles"][1] == 2
    assert sum(col["histogram"]) == 3
    assert report["file_bytes"] > 0


def test_empty(engine, datasets):
    report = profile(engine, datasets("empty", {"x": pa.array([], type=pa.float64())}))
    col = report["columns"][0]
    assert report["rows"] == 0
    assert col["mean"] is None
    assert col["null_percent"] == 0
    assert sum(col["histogram"]) == 0


@pytest.mark.parametrize(
    "values", [[None, None], [7.0, 7.0], [math.nan, math.inf, -math.inf], [-1e308, 1e308]]
)
def test_edge_distributions(engine, datasets, values):
    report = profile(engine, datasets("edge", {"x": pa.array(values, type=pa.float64())}))
    col = report["columns"][0]
    assert sum(col["histogram"]) == sum(v is not None and math.isfinite(v) for v in values)


def test_quoted_identifier(engine, datasets):
    report = profile(engine, datasets("quoted", {'a"b': [1, 2]}))
    assert report["columns"][0]["mean"] == 1.5


def test_histogram_sparse_bins(engine, datasets):
    report = profile(engine, datasets("sparse", {"x": [0.0, 7.0, None]}))
    assert report["columns"][0]["histogram"] == [1, 0, 0, 0, 0, 0, 0, 1]
