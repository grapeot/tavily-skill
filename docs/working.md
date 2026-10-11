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

- Added multi-query batch mode to `search`: repeatable `--query`, optional positional `query`, `--concurrency N` (default 4) and `--serial`, execution via `ThreadPoolExecutor` over the shared SDK client. One auto-named JSON file per query (index suffix on collision), exactly one batch status envelope on stdout, `--output` rejected in batch mode. The search `--stdout` flag this entry originally paired with `--output` was removed on 2026-10-10. Partial failure exits 0 with per-query errors and a stderr warning; all-failure exits 1; usage errors exit 2.
- Unified the batch envelope with the sibling `firecrawl-skill`: replaced top-level `mode`/flat counts with `output_mode: "batch"` and nested `summary` (`query_count`/`success_count`/`failed_count`/`credits_used`), added `output_dir` and an `input` block, and changed per-query `error` to `{"http_status", "error"}`. Also reject empty/whitespace-only queries (exit 2) and stop the thread pool from blocking on Ctrl-C so the process returns 130 promptly.
- Added an opt-in latency benchmark (`benchmarks/latency.py`, `benchmarks/README.md`) comparing standalone, `batch-parallel`, and `batch-serial` search with real API calls. Gated by `RUN_TAVILY_LATENCY=1`; unique per-run queries defeat provider caching; children are pointed at a temporary `TAVILY_CLI_OUTPUT_DIR`. Added offline unit tests for the pure helpers.
- Documented the performance model: a "Performance" section in the README and a "Speed optimization" section in the skill covering batch reuse of process/credential setup and recommending a raw local `TAVILY_API_KEY` so the CLI skips the ~0.9s `op read`.

## 2026-10-10

- Removed `--stdout` from `search` and `extract`; passing it exits 2 as an unrecognized argument before sending any request. Successful `search` and `extract` calls always write the full JSON payload to a file and return status JSON on stdout. `usage --stdout` remains unchanged and inlines output. `--output` remains supported for single runs and writes to the caller-chosen path without implying shared corpus coverage.
- Repaired documentation across README, skill, PRD, RFC, test strategy, and working notes: added executable single and batch Python examples checking return codes before parsing and reading exact returned paths; replaced invalid README single-status JSON with illustrative values and the source-defined schema (including `payload_bytes` and `summary.failed_count: null`); narrowed single-query parity to file-mode behavior; clarified caller-side bounded selection and custom output semantics; and documented offline synthetic example validation.

## Lessons Learned

- Default artifact directory resolves from current working directory (`./tmp/tavily/`); override with `TAVILY_CLI_OUTPUT_DIR` when jobs must isolate outputs.
- Prefer `.venv/bin/python -m tavily_skill` or `scripts/run_cli.sh` over relying on a shell activation side effect; direct interpreter paths survive workspace-level routing changes better.
- Enforce untrusted upstream-field exclusions in response normalization rather than relying on agent instructions.
- Reserve batch output filenames on the main thread before dispatching workers; deriving names inside threads races on the shared timestamp+slug and can silently overwrite files.
- Time-based tests for parallelism should compare measured parallel wall time against measured serial wall time from the same test, not against an absolute constant, so slow CI machines don't produce false failures.
- Latency benchmarks must use unique queries per run. Reusing identical queries let a warm provider cache make a batch read faster than a single cold call, which is not the effect being measured.
- An explicit `--output` path is not the shared snapshot directory. Callers who want corpus coverage must write into `TAVILY_CLI_OUTPUT_DIR` or `./tmp/tavily/`, not an arbitrary file path.
- Exact returned paths: Open the `output_path` returned by this invocation instead of globbing for newest files by mtime, which can select another concurrent job's payload.
- Nonzero exit before parsing: Inspect the subprocess return code before `json.loads(stdout)`; exit 2 for invalid flags or exit 1 for API/write failures may leave stdout empty. Report stderr rather than masking the failure with a JSON parsing error.
- Large payload selection: Mandatory file output keeps result bodies off stdout, but callers must bound result counts and string lengths in code. Printing or pasting entire payload files still exhausts LLM context windows.
