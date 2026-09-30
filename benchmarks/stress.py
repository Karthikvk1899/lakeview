import json
import math
import tempfile
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from lakeview.core.engine import Engine
from lakeview.core.profiler import profile

root = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix="large-profile-", dir=root) as folder:
    file = Path(folder) / "large.parquet"
    schema = pa.schema([("id", pa.int64()), ("metric", pa.float64()), ("payload", pa.string())])
    with pq.ParquetWriter(file, schema, compression="NONE", use_dictionary=False) as writer:
        for part in range(120):
            start = part * 10_000
            writer.write_table(
                pa.table(
                    {
                        "id": range(start, start + 10_000),
                        "metric": [float(i % 100) for i in range(start, start + 10_000)],
                        "payload": ["x" * 2048] * 10_000,
                    },
                    schema=schema,
                )
            )
    start = time.perf_counter()
    with Engine("128MB", threads=2) as engine:
        result = profile(engine, str(file))
    assert result["rows"] == 1_200_000
    assert math.isclose(result["columns"][1]["mean"], 49.5)
    print(
        json.dumps(
            {
                "rows": result["rows"],
                "file_bytes": result["file_bytes"],
                "process_rss_bytes_after_scan": result["process_rss_bytes"],
                "seconds_including_engine": time.perf_counter() - start,
                "memory_limit": "128MB",
                "threads": 2,
                "layout": "Uncompressed Parquet, 120 batches, 2048-byte constant payload; column projection applies.",
            },
            indent=2,
        )
    )
