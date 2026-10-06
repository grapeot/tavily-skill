# Test Strategy

## Unit tests (default)

Run from project root:

```bash
uv venv .venv
uv pip install -e '.[dev]'
uv run pytest tests/ -v
```

Coverage targets:

- Argument parsing defaults and validation conflicts (`search` date modes, `extract` chunks without `--query`, mutually exclusive `--stdout`/`--output`, `usage` timeout).
- Batch search mode: positional vs `--query` mutual exclusion, missing query, `--output`/`--stdout` rejection, non-positive `--concurrency`, and `--serial` overriding `--concurrency`.
- `_build_search_request`, `_build_extract_request`: Tavily SDK request shapes including `days=None` when absolute dates are set, and per-query overrides in batch mode.
- Batch execution: one auto-named file per query, index suffix on filename collision, and a single batch status envelope with per-query `{query, output_path, summary, error}` entries.
- Batch concurrency: a stubbed search that sleeps shows concurrent queries finish materially faster than `--serial` wall time.
- Batch error semantics: partial failure returns exit 0 with per-query errors and a stderr warning; all-queries failure returns exit 1; argparse usage errors return exit 2.
- Response normalization: `result_count`, `failed_count`, `image_count`, stable envelope `{command, input, data}`.
- `_normalize_usage_response`: plan/limit/remaining derivation, per-endpoint breakdown, and missing-field tolerance.
- `_emit_payload`: stdout-only vs file mode (status JSON on stdout, human hints on stderr).
- `_resolve_output_path`: respects `--stdout`, explicit `--output`, and default filename pattern under `get_default_output_dir()` (including `usage`).

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

## End-to-end

No browser or MCP harness in this repo; agents validate by running the CLI against real queries during manual smoke sessions.
