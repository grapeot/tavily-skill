# Test Strategy

## Unit tests (default)

Run from project root:

```bash
uv venv .venv
uv pip install -e '.[dev]'
uv run pytest tests/ -v
```

Coverage targets:

- Argument parsing defaults and validation conflicts (`search` date modes, `extract` chunks without `--query`, `usage` timeout, and `usage` rejecting `--stdout` with `--output`).
- `search` and `extract` reject `--stdout` before any client or network call. Successful single and batch runs write files and return status only. `usage --stdout` still inlines JSON.
- Batch search mode: positional vs `--query` mutual exclusion, missing/empty/whitespace-only queries, `--output` rejection, non-positive `--concurrency`, and `--serial` overriding `--concurrency`.
- `_build_search_request`, `_build_extract_request`: Tavily SDK request shapes including `days=None` when absolute dates are set, and per-query overrides in batch mode.
- Batch execution: one auto-named file per query, index suffix on filename collision, and a single canonical batch envelope (`command`, `status`, `output_mode: "batch"`, `output_dir`, `input`, nested `summary` counts, `results`) with per-query `{query, output_path, summary, error}` entries.
- Batch concurrency: a stubbed search that sleeps shows concurrent queries finish materially faster than `--serial` wall time.
- Batch error semantics: partial failure returns exit 0 with per-query `{http_status, error}` entries and a stderr warning; all-queries failure returns exit 1; argparse usage errors return exit 2; Ctrl-C returns exit 130.
- Response normalization: `result_count`, `failed_count`, `image_count`, stable envelope `{command, input, data}`.
- `_normalize_usage_response`: plan/limit/remaining derivation, per-endpoint breakdown, and missing-field tolerance.
- `_emit_payload`: `usage --stdout` inlines JSON; file mode prints status JSON on stdout and a human hint on stderr.
- `_resolve_output_path`: `usage --stdout` skips the file, explicit `--output` wins, and the default filename pattern stays under `get_default_output_dir()` (including `usage`).
- Benchmark pure helpers (`tests/test_bench_latency.py`): `benchmarks/latency.py` argument defaults and validation, unique-query generation, median and speedup computation, report shaping, command/env construction, the `RUN_TAVILY_LATENCY` gate, and the skip path. `subprocess.run` is mocked throughout, so these tests make no API calls and spend no credits.

These tests must not access the network and must not require API keys.

## Integration tests (`pytest -m integration`)

Enable only when intentionally spending Tavily credits:

```bash
export RUN_TAVILY_INTEGRATION=1
export TAVILY_API_KEY=tvly-...
uv run pytest tests/ -v -m integration
```

Alternatively unset `TAVILY_API_KEY` and rely on `ONEPASSWORD_TAVILY_REFERENCE` plus a logged-in 1Password CLI — CI should prefer explicit env vars, not shared vault paths.

Integration tests exercise:

- End-to-end `search` and `extract` subprocess invocations (`python -m tavily_skill`).
- `usage` is exercised at unit level through a monkeypatched `_fetch_usage`; it is not part of the paid integration tier because it consumes no credits.
- Optional verification that the SDK receives the resolved API key when using a fake `tavily` module on `PYTHONPATH`.

## Documentation example validation (offline synthetic)

Validate the [single-search snippet](../skills/skill_tavily.md#reading-search-results-safely-in-python-single-search) and [batch snippet](../skills/skill_tavily.md#reading-batch-search-results-safely-in-python) using synthetic subprocess outputs and temporary payload files:

- Mock the subprocess runner to return fixture status JSON and diagnostics without invoking the CLI or network.
- Point `output_path` at synthetic `{command, input, data}` payload files. Verify that the snippets open those exact returned paths, including relative and custom-directory paths, without globbing or sorting by mtime.
- Verify that nonzero return codes (exit 2 for invalid flags like removed `--stdout`, exit 1 for API/write failures) print stderr and abort before JSON parsing or file reads, even with empty or invalid stdout.
- Validate single `command: "search"`, `status: "ok"`, `output_mode: "file"`, and nonempty `output_path`. For batch, validate `command: "search"`, `output_mode: "batch"`, and `status` of `ok` or `partial`; the path belongs to each entry, not the top level.
- Verify bounded result counts and string lengths, including fallback from missing `raw_content` to snippet `content`, rather than printing complete payloads.
- Verify that batch processing opens only entries with `error is None` and a nonempty `output_path`, skipping failed queries without attempting file reads. Partial success exits 0; all-failure exits 1 and must stop before parsing.

This documentation validation checks caller-side routing logic against offline fixtures. It is separate from the existing automated CLI unit suite and from paid live integration tests. It does not establish real API behavior; record only checks actually executed.

## End-to-end

No browser or MCP harness in this repo; agents validate by running the CLI against real queries during manual smoke sessions.
