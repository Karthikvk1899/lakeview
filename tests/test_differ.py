import pyarrow as pa
import pytest

from lakeview.core.differ import diff
from lakeview.core.engine import LakeviewError


def test_keyed(engine, datasets):
    a = datasets("a", {"id": [1, 2, 3], "value": [10, 20, 30]})
    b = datasets("b", {"id": [2, 3, 4], "value": [21, 30, 40]})
    report = diff(engine, a, b, ["id"])
    assert (report["added"], report["removed"], report["modified"], report["unchanged"]) == (
        1,
        1,
        1,
        1,
    )
    assert report["metrics"]["value"]["delta"]["mean"] == pytest.approx(31 / 3)


def test_multiset_duplicates(engine, datasets):
    a = datasets("a", {"v": [1, 1, 2, None]})
    b = datasets("b", {"v": [1, 2, 2, None]})
    report = diff(engine, a, b)
    assert (report["added"], report["removed"], report["unchanged"]) == (1, 1, 3)
    assert report["modified"] is None


def test_null_keys_and_values(engine, datasets):
    a = datasets("a", {"id": [None, 2], "v": [1, None]})
    b = datasets("b", {"id": [None, 2], "v": [2, None]})
    report = diff(engine, a, b, ["id"])
    assert (report["modified"], report["unchanged"]) == (1, 1)


@pytest.mark.parametrize("keys", [["id"], ["missing"], ["id", "id"]])
def test_bad_keys(engine, datasets, keys):
    a = datasets("a", {"id": [1, 1]})
    b = datasets("b", {"id": [1, 2]})
    with pytest.raises(LakeviewError):
        diff(engine, a, b, keys)


def test_schema_drift(engine, datasets):
    a = datasets("a", {"id": [1], "v": [1], "old": [True]})
    b = datasets("b", {"id": [1], "v": [1.0], "new": [True]})
    report = diff(engine, a, b, ["id"])
    assert report["schema"]["added"] == {"new": "BOOLEAN"}
    assert report["schema"]["removed"] == {"old": "BOOLEAN"}
    assert report["schema"]["changed"]["v"] == {"source": "BIGINT", "target": "DOUBLE"}
    assert report["different"]
    assert report["modified"] == 0


def test_incompatible_bags(engine, datasets):
    report = diff(engine, datasets("a", {"v": [1]}), datasets("b", {"v": [1.0]}))
    assert report["added"] == report["removed"] == 1


def test_column_order_irrelevant(engine, datasets):
    report = diff(engine, datasets("a", {"a": [1], "b": [2]}), datasets("b", {"b": [2], "a": [1]}))
    assert not report["different"]


def test_empty_bags(engine, datasets):
    a = datasets("a", {"v": pa.array([], type=pa.int64())})
    b = datasets("b", {"v": pa.array([], type=pa.int64())})
    assert not diff(engine, a, b)["different"]


def test_composite_keys(engine, datasets):
    a = datasets("a", {"a": [1, 1], "b": [1, 2], "v": [1, 2]})
    b = datasets("b", {"a": [1, 1], "b": [1, 2], "v": [1, 3]})
    assert diff(engine, a, b, ["a", "b"])["modified"] == 1


def test_large_integer_exact(engine, datasets):
    a = datasets("a", {"v": [2**60]})
    b = datasets("b", {"v": [2**60 + 1]})
    assert diff(engine, a, b)["added"] == 1
