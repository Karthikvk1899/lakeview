from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from lakeview.core.engine import Engine


@pytest.fixture
def engine() -> Iterator[Engine]:
    with Engine() as value:
        yield value


@pytest.fixture
def datasets(tmp_path: Path) -> Any:
    def write(name: str, data: dict[str, Any]) -> str:
        path = tmp_path / f"{name}.parquet"
        pq.write_table(pa.table(data), path)
        return str(path)

    return write
