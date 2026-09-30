# Security

lakeview processes local data and SQL in your user account. It is not a sandbox.
Only run SQL you trust: a SELECT can read files and invoke engine functions.
Do not run untrusted SQL on a host with credentials or private data.

Database inputs attach read-only. Parquet/CSV/Arrow inputs are scanned without
modification. Operations may spill sensitive data into an OS temporary directory;
lakeview removes it on normal exit. Forced termination can leave temporary files.
Use encrypted storage and an appropriate TMPDIR/TEMP for sensitive workloads.

Reports include schema and aggregates; query output includes actual values.
Review these before posting them to public CI logs or pull requests.

Report vulnerabilities through GitHub's private vulnerability reporting when
available. Otherwise open an issue requesting a private contact without exploit
details, secrets, or private datasets.
