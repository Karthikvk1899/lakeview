# Contributing

Reproduce a small data problem first. Synthetic data is welcome; customer data is not.

```sh
git clone https://github.com/Karthikvk1899/lakeview.git
cd lakeview
uv sync --locked
uv run pytest --cov=lakeview --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict
```

For a bug, include lakeview/Python versions, OS, the command, expected output,
and the smallest synthetic dataset that reproduces it. Report memory limits
and available temporary disk space when relevant.

Tests should protect semantics: duplicate counts, NULL equality, type drift,
empty inputs, identifiers, and supported formats. Never silently coerce keys
or replace exact row equality with hashes. Add a regression test with fixes.

Use conventional commits (`fix:`, `feat:`, `docs:`, `test:`). Keep a pull request
focused and describe observable behavior, limitations, and validation.
Performance claims need the benchmark command, hardware, versions, and raw samples.

## Release process

Update the version, run CI, and publish a matching GitHub release. The release
workflow builds wheels, a source distribution, and platform bundles, smoke-tests
the bundles, and attaches SHA256 checksums. PyPI is opt-in: register this repository,
`release.yml`, and the `pypi` environment as a trusted publisher on PyPI, then set
the repository variable `PYPI_PUBLISH=true`. Package name availability and publisher
authorization must be established before enabling it. Do not store PyPI tokens in code.
