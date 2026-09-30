"""Generate synthetic local inputs for the README demo."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

folder = Path("demo")
folder.mkdir(exist_ok=True)
pq.write_table(
    pa.table({"id": [1, 2, 3], "revenue": [100.0, 200.0, 300.0]}), folder / "prod.parquet"
)
pq.write_table(
    pa.table(
        {"id": [2, 3, 4], "revenue": [250.0, 300.0, 400.0], "region": ["east", "west", "east"]}
    ),
    folder / "staging.parquet",
)
print("Created demo/prod.parquet and demo/staging.parquet")
