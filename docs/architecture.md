# Architecture and operational limits

`cli.py` translates arguments, renders output, and maps expected failures to exit 2.
`Engine` owns the connection, Arrow handles, attached databases, and spill directory.
`profiler.py` and `differ.py` return plain reports that terminal/Markdown/JSON formatters consume.

## Profiling

Three passes: finite numeric magnitudes; counts and moments with approximate quartiles;
eight equal-width numeric bins. Constant values occupy the first bin. Empty/all-null
columns have unavailable moments, zero bins, and a zero null percentage for zero rows.
NaN and infinities are counted separately from NULL and excluded from moments and bins.
Variance is population variance. Schema types are DuckDB logical types.

DOUBLE conversion is deliberate for descriptive statistics. Original values and types
remain in row comparisons. Overflowed output floats are JSON null / unavailable in
formatted reports. Histograms and quantiles do not replace full data validation.

## Comparison

Unique keyed joins use `IS NOT DISTINCT FROM`; NULL keys can match but duplicate
NULL/composite keys fail uniqueness checks. Added/removed counts come from total minus
matched rows. Modified is the count of matched rows with any null-safe value difference
among shared, identical-type non-key columns. No type coercion guesses.

Unkeyed comparisons use symmetric `EXCEPT ALL` projections with columns aligned by name.
Schema incompatibility means no comparable full records, so all rows become additions
and removals. Numerical drift uses finite summaries independently of row pairing.

Nested types follow DuckDB's comparison support. Unsupported operations return clear
engine errors. CSV names/types follow DuckDB inference, including its header normalization.
Case-distinct/duplicate input column names are not a supported schema contract.
Inputs must remain unchanged while commands run; there is no cross-file snapshot isolation.

## Resource model

No persistent database artifact is created. Read-only DuckDB inputs cannot be modified
by attached-table writes. SELECT-only validation excludes common write statements and
multi-statement queries, but is not a security sandbox; trusted SQL is required.
Arrow queries yield at most 8,192 rows per batch, although a single wide row can itself
be large. Terminal previews cap retained rows. Aggregations and joins have their own
engine memory costs. `memory_limit` is not a hard process memory cap.

Temporary conversion and spill require disk space. Cancellation/crashes can leave
OS temporary directories. Use an appropriate encrypted temporary volume for sensitive
data. Large inputs are supported through scans, batches, and spill, not by a promise
of bounded RSS for arbitrary schemas or SQL.

## Validation

The CI matrix covers Python 3.11–3.14 on Linux, macOS, and Windows. The strict mypy
check covers the shipped Python package; Arrow's untyped interface is an explicit
boundary. Ruff checks/formatting and a minimum 85% test coverage gate run on each job.
Release jobs rebuild packages, run tests, and build/smoke-test platform bundles.
