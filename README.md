# lakeview — The missing CLI for local data profiling, semantic diffing, and fast SQL.

[![CI](https://github.com/Karthikvk1899/lakeview/actions/workflows/ci.yml/badge.svg)](https://github.com/Karthikvk1899/lakeview/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://github.com/Karthikvk1899/lakeview/blob/main/pyproject.toml)
[![Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-green)](https://github.com/Karthikvk1899/lakeview/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/lakeview-cli)](https://pypi.org/project/lakeview-cli/)

Your dbt model ran. The row count looks fine. Something still changed.

You can open a notebook, load two DataFrames, remember how to compare NULLs,
then discover that duplicate rows broke your join. Or start a warehouse just
to inspect two files already on your laptop.

For the small-file, two-second check you wanted in the first place:

```sh
lakeview diff prod.parquet staging.parquet --on id
```

**Exact row comparisons. Duplicate-aware counts. Read-only inputs. No account.**

![Actual Rich terminal output from the synthetic demo](https://raw.githubusercontent.com/Karthikvk1899/lakeview/main/docs/demo.svg)

```diff
$ lakeview diff prod.parquet staging.parquet --on id
+ added rows:      1
- removed rows:    1
! modified rows:   1
  unchanged rows:  1
+ schema: region VARCHAR
! revenue mean: 200.00 -> 316.67
```

The condensed example above comes from the three-row [demo generator](https://github.com/Karthikvk1899/lakeview/blob/main/examples/make_demo.py).
The CLI renders insertions in green, deletions in red, and modifications in yellow.

## Install and try it

Python 3.11 or newer. Install from PyPI:

```sh
pip install lakeview-cli
lakeview --help
```

On Apple Silicon macOS or x86-64 Linux, install the standalone bundle through the
[official Homebrew tap](https://github.com/Karthikvk1899/homebrew-lakeview):

```sh
brew install Karthikvk1899/lakeview/lakeview
```

The tap's macOS install is checked in CI. Other platforms can use PyPI, or a wheel /
platform bundle from [Releases](https://github.com/Karthikvk1899/lakeview/releases).
PyPI publishing uses GitHub Actions trusted publishing.

```sh
git clone https://github.com/Karthikvk1899/lakeview.git
cd lakeview
uv sync --locked
uv run python examples/make_demo.py
uv run lakeview profile demo/prod.parquet
uv run lakeview diff demo/prod.parquet demo/staging.parquet --on id
uv run lakeview query 'SELECT avg(revenue) FROM data' demo/staging.parquet
```

## Three commands, useful defaults

| Command | What you get |
| --- | --- |
| `profile` | Schema, exact row/null counts, null rates, mean, population variance, min/max, approximate quartiles, eight-bin histograms, file size and process RSS |
| `diff` | Schema additions/removals/type changes, exact row deltas, mean/variance/min/max drift |
| `query` | DuckDB SELECT queries, bounded terminal previews, streaming JSONL output |

```sh
lakeview profile events.parquet --format json
lakeview profile 'warehouse.duckdb::main.orders' --memory-limit 256MB
lakeview diff yesterday.csv today.csv --on account_id,event_id --format markdown
lakeview diff baseline.arrow candidate.arrow --fail-on-change
lakeview query 'SELECT f1.id FROM f1 JOIN f2 USING (id)' left.parquet right.csv
lakeview query 'SELECT * FROM data ORDER BY id' events.parquet --format jsonl > rows.jsonl
```

Formats: Parquet (`.parquet`, `.pq`), CSV/TSV with headers, DuckDB (`.duckdb`, `.db`),
and Arrow IPC file/stream (`.arrow`, `.ipc`) / Feather V2 (`.feather`). A database
with one table can omit the selector. With several tables, use `file.duckdb::schema.table`.
The first query input is `f1` (also `data`), followed by `f2`, `f3`, etc.

The terminal query preview defaults to 100 rows; change it with `--limit`.
JSONL streams every row in batches of 8,192. Decimal/HUGEINT and temporal values
serialize as strings to preserve precision. SQL NULL and non-finite floats become
JSON `null`. Use ORDER BY when output order matters.

## What does “different” mean?

| Case | Behavior |
| --- | --- |
| With `--on` | Keys must exist with identical types and be unique on each side. Composite keys supported; NULL matches NULL. Duplicate keys produce an error instead of a many-to-many join. |
| Without `--on` | Exact multiset comparison via `EXCEPT ALL`: duplicate multiplicities count. A changed row is a removal plus an addition; modified is unavailable. |
| Column order | Ignored for equality. |
| Schema drift with keys | Reported separately. Modified counts compare shared, identical-type non-key columns only. A changed-type column is not silently cast. |
| Schema drift without keys | Incompatible schemas make all source rows removed and all target rows added. |
| Floating values | Exact DuckDB equality for row comparisons, including its NaN semantics. No rounding or tolerance is applied. |
| Numeric summaries | Finite values only, converted to DOUBLE; high-precision decimals/integers may round in statistics, but row comparisons retain their original types. |

Exit codes: **0** success, **1** differences when `--fail-on-change` is enabled,
**2** input, SQL, or execution error. Without `--fail-on-change`, a successful diff
returns 0 even if data changed. Schema drift counts as a difference.

## Performance, measured

One million rows, three columns, 11.6 MB Parquet. Windows build 26200, eight logical
CPUs, Python 3.11.15, DuckDB 1.5.6, Arrow 23.0.1, Pandas 3.0.6.
Medians of three fresh processes; OS file cache may be warm. Peak RSS is sampled
every 10 ms. [Raw samples](https://github.com/Karthikvk1899/lakeview/blob/main/docs/benchmarks/windows-1m.json) and [benchmark script](https://github.com/Karthikvk1899/lakeview/blob/main/benchmarks/run.py).

| Workflow | Startup probe | Full operation | Peak RSS during operation |
| --- | ---: | ---: | ---: |
| lakeview | 382 ms (`--help`) | 1,314 ms (`profile --format json`) | 131.5 MiB |
| Pandas | 737 ms (`import pandas`) | 995 ms (`read_parquet`, `describe`, null counts) | 173.4 MiB |
| Spark | Not measured | Not measured | Not measured |

These operations are not feature-equivalent: Pandas `describe` also computes distinct
categorical summaries; lakeview computes histograms. Startup probes are different
operations too. This fixture favors Pandas on elapsed time. lakeview's value is a
ready-to-use CLI, explicit diff semantics, and a spill-capable engine.

**There is no universal “under 200 ms” promise.** Full statistics require scans;
storage, data shape, string width, CPU, and startup matter. Quantiles are approximate.
CSV performs full-file type inference for consistent types, adding work. IPC streams
are converted batchwise into temporary Parquet for repeatable scans.

```sh
uv run --extra benchmark python benchmarks/run.py --rows 1000000 --repeats 3
```

`--memory-limit` controls DuckDB's buffer manager, not total process RSS. Arrow,
Python, and some engine allocations sit outside it. Large joins and sorts can spill
to the temporary directory; adequate disk space is required. Resource exhaustion is
reported as a CLI error, not a guarantee that every workload fits any memory limit.
The profile's RSS is a process snapshot after scanning, not a peak measurement.

A separate large-file smoke test profiled **2.49 GB of uncompressed Parquet**
(1.2 million rows) in **3.10 seconds**, using `--memory-limit 128MB --threads 2`.
Process RSS after scanning was 144.5 MiB. This fixture has a constant 2,048-byte
string payload and benefits from column projection; it is not representative of
all 2.49 GB files. [Raw result](https://github.com/Karthikvk1899/lakeview/blob/main/docs/benchmarks/large-parquet.json).

## Put the diff in a pull request

The job below assumes your existing build produced `baseline.parquet` and
`candidate.parquet` in the workspace. Use `pull_request`, never run untrusted PR
code with a privileged `pull_request_target` token. Fork PRs generally cannot write
comments with their read-only token; they can still retain a job summary.

```yaml
permissions:
  contents: read
  pull-requests: write
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: '3.11'
  - run: pip install lakeview-cli==0.1.1
  - name: Compute report
    shell: bash
    run: |
      lakeview diff baseline.parquet candidate.parquet --on id --format markdown > diff.md
      cat diff.md >> "$GITHUB_STEP_SUMMARY"
  - uses: actions/github-script@v7
    if: github.event_name == 'pull_request' && github.event.pull_request.head.repo.fork == false
    with:
      script: |
        const fs = require('fs');
        const body = fs.readFileSync('diff.md', 'utf8');
        await github.rest.issues.createComment({
          ...context.repo,
          issue_number: context.issue.number,
          body: body.slice(0, 60000)
        });
  - name: Fail on data changes
    run: lakeview diff baseline.parquet candidate.parquet --on id --fail-on-change
```

Reports can expose business aggregates. Review what is appropriate for your repository.
Markdown report values are escaped and passed as file contents, not interpolated
into executable JavaScript or shell commands.

## Under the hood

Each command owns an in-memory DuckDB connection and a temporary spill directory.
Parquet/CSV scans stay in DuckDB; IPC files use Arrow Dataset scans. IPC streams are
written one record batch at a time to temporary Parquet. DuckDB databases attach
read-only. Normal exit closes resources and removes temporary files.

Profiling computes finite magnitudes, aggregate statistics, then equal-width histogram
bins in separate vectorized passes. Scaling prevents intermediate variance overflow;
statistics outside representable floating-point range render as unavailable. Diffing
uses exact comparisons, not hash equality. Python receives summaries or query batches,
never a whole input DataFrame.

See [architecture and limits](https://github.com/Karthikvk1899/lakeview/blob/main/docs/architecture.md), [security](https://github.com/Karthikvk1899/lakeview/blob/main/SECURITY.md), and
[contributing](https://github.com/Karthikvk1899/lakeview/blob/main/CONTRIBUTING.md). This is an initial beta release. It does not include
remote storage, fuzzy matching, row samples, or automatic key discovery.

## Help make local data work less tedious

Try it on a real model output. Open an issue with a synthetic reproduction when the
semantics surprise you. Contributions around datasets, profiling accuracy, and
reproducible performance are especially useful. If it earns a place in your workflow,
a star helps other data engineers find it.

Apache-2.0. Built with [DuckDB](https://duckdb.org/) and [Apache Arrow](https://arrow.apache.org/).
