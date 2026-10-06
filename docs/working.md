# Changelog

## 2026-05-10

- Initial scaffold: Tavily search/extract CLI, credential-safe defaults (env / optional `op` reference), English docs and SKILL.
- Documentation uses paths relative to repository root only.

## 2026-05-28

- Renamed the workspace checkout to `adhoc_jobs/tavily_skill/` and retired the old workspace-level shim; canonical invocation is `.venv/bin/python -m tavily_skill` or `scripts/run_cli.sh` from the standalone repo.

## 2026-07-29

- Removed the search answer option and answer fields from requests, normalized payloads, status summaries, and schemas.

## 2026-09-04

- Documented `TAVILY_CLI_OUTPUT_DIR` in the skill file (new "First-time setup" section: recommend a dedicated persistent output directory once during initial setup), README, and `.env.example`.

## 2026-10-03

- Added `usage` subcommand: calls `GET https://api.tavily.com/usage` (the SDK has no method for it), normalizes plan/usage into the standard envelope, and derives `data.remaining_credits` from `plan_limit - plan_usage`. Same credential chain, validation, and file-first output as `search`/`extract`.

## 2026-10-05

- Added multi-query batch mode to `search`: repeatable `--query`, optional positional `query`, `--concurrency N` (default 4) and `--serial`, execution via `ThreadPoolExecutor` over the shared SDK client. One auto-named JSON file per query (index suffix on collision), exactly one batch status envelope on stdout, `--output`/`--stdout` rejected in batch mode. Partial failure exits 0 with per-query errors and a stderr warning; all-failure exits 1; usage errors exit 2.
- Unified the batch envelope with the sibling `firecrawl-skill`: replaced top-level `mode`/flat counts with `output_mode: "batch"` and nested `summary` (`query_count`/`success_count`/`failed_count`/`credits_used`), added `output_dir` and an `input` block, and changed per-query `error` to `{"http_status", "error"}`. Also reject empty/whitespace-only queries (exit 2) and stop the thread pool from blocking on Ctrl-C so the process returns 130 promptly.
- Added an opt-in latency benchmark (`benchmarks/latency.py`, `benchmarks/README.md`) comparing standalone, `batch-parallel`, and `batch-serial` search with real API calls. Gated by `RUN_TAVILY_LATENCY=1`; unique per-run queries defeat provider caching; children are pointed at a temporary `TAVILY_CLI_OUTPUT_DIR`. Added offline unit tests for the pure helpers.
- Documented the performance model: a "Performance" section in the README and a "Speed optimization" section in the skill covering batch reuse of process/credential setup and recommending a raw local `TAVILY_API_KEY` so the CLI skips the ~0.9s `op read`.

## Lessons Learned

- Default artifact directory resolves from current working directory (`./tmp/tavily/`); override with `TAVILY_CLI_OUTPUT_DIR` when jobs must isolate outputs.
- Prefer `.venv/bin/python -m tavily_skill` or `scripts/run_cli.sh` over relying on a shell activation side effect; direct interpreter paths survive workspace-level routing changes better.
- Enforce untrusted upstream-field exclusions in response normalization rather than relying on agent instructions.
- Reserve batch output filenames on the main thread before dispatching workers; deriving names inside threads races on the shared timestamp+slug and can silently overwrite files.
- Time-based tests for parallelism should compare measured parallel wall time against measured serial wall time from the same test, not against an absolute constant, so slow CI machines don't produce false failures.
- Latency benchmarks must use unique queries per run. Reusing identical queries let a warm provider cache make a batch read faster than a single cold call, which is not the effect being measured.
