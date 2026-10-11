# Tavily Skill — Architecture Decisions

Each section records a design decision embodied in the codebase, with the context that motivated it, the alternatives considered, and the consequences of the choice.

## 1. Stable envelope over raw SDK passthrough

**Decision.** All responses are wrapped in `{command, input, data}` before reaching stdout or the output file. The envelope fields are hand-picked; they do not mirror the raw SDK dictionary.

**Context.** The Tavily Python SDK can change its response shape across versions — rename fields, restructure nested objects, add or remove optional keys. If agents embed parsing logic that depends on a particular SDK version's return shape, a version bump breaks them silently.

**What was rejected.** Passing the SDK response through unchanged, relying on documentation or convention to keep agents in sync with the SDK version.

**Consequences.** Downstream parsers see a stable surface regardless of SDK version. The cost is that new SDK fields don't automatically appear in the envelope; they must be explicitly added to the normalization functions. This is deliberate — it makes SDK upgrades an explicit, reviewable change rather than a silent surface expansion.

## 2. File-first output for search and extract

**Decision.** File output is mandatory for `search` and `extract`. Every successful run writes the full JSON payload to disk and prints a compact status object to stdout; `--stdout` is no longer supported on content commands. `usage --stdout` remains the exception and may inline its small usage payload directly.

**Context.** In agent orchestration loops, subprocess stdout may be captured and forwarded into subsequent LLM calls. A search for "latest AI developments" can return hundreds of kilobytes of markdown content. If that payload lands in the agent's context window on every iteration — especially in a loop — it wastes tokens and dilutes signal.

**What was rejected.** Inlining search and extract response bodies on stdout.

**Consequences.** Successful single content calls return a small status JSON (`{command, status, output_mode, output_path, payload_bytes, summary, payload_schema}`) rather than the full normalized file payload (`{command, input, data}`). The status object retains `payload_schema` so callers know the data shape before opening the file, and points to a file retaining result bodies without mirroring every internal SDK key.

Callers must follow an exit-before-parse and exact-path selection contract:
1. **Exit before parse**: Verify `proc.returncode == 0` before calling `json.loads(proc.stdout)`. On nonzero exits (exit 2 for invalid flags like removed `--stdout`, exit 1 for API/write failures), report stderr and abort; stdout is not guaranteed to contain status JSON.
2. **Exact path resolution**: Open the exact `output_path` returned in that invocation's status envelope, rather than guessing paths via globbing or mtime ordering. For batch partial success (exit 0), open only entries with `error is None` and a nonempty `output_path`.
3. **In-code bounded selection**: Mandatory file output keeps result bodies off stdout, but does not automatically protect LLM context windows if callers dump entire files into prompts. Select bounded fields (for example, top N results and truncated excerpts) in code.

Explicit `--output` overrides both default `./tmp/tavily/` and `TAVILY_CLI_OUTPUT_DIR`. Neither setting a custom directory nor specifying explicit output guarantees a canonical shared raw corpus. See the [single-search example](../skills/skill_tavily.md#reading-search-results-safely-in-python-single-search) and [batch example](../skills/skill_tavily.md#reading-batch-search-results-safely-in-python) for executable implementations.

## 3. 1Password bridge without baked vault identifiers

**Decision.** The CLI supports optional `op read <reference>` credential resolution, but the reference string itself is never stored in the codebase. Operators set `ONEPASSWORD_TAVILY_REFERENCE` in their environment.

**Context.** Early iterations referenced concrete `op://` vault paths that made sense in a private workspace but leaked internal infrastructure layout when the repository was opened. For an open-source project, the code must not know the operator's vault structure.

**What was rejected.**
- Hard-coding a vault reference path in the source or in committed `.env.example` — leaks vault layout if the repo is forked or mirrored.
- Requiring the operator to export `TAVILY_API_KEY` as plaintext and forgoing 1Password integration entirely — works but removes ergonomics for users who already use `op` CLI.
- Using 1Password service account tokens or Connect SDK — adds infrastructure dependencies that don't belong in a single-file CLI.

**Consequences.** The credential resolution chain is `TAVILY_API_KEY` → `ONEPASSWORD_TAVILY_REFERENCE` via `op read` → `RuntimeError`. CI pipelines inject the API key directly; desktop operators can use their 1Password vault without exposing key material in shell history. The `op read` subprocess is wrapped in a 10-second timeout and catches both `TimeoutExpired` (hanging `op` process) and `FileNotFoundError` (`op` CLI not installed) to degrade gracefully.

## 4. Working-directory-relative artifact roots

**Decision.** Default output anchors under `Path.cwd() / "tmp" / "tavily"`. `.env` discovery walks up from CWD through parent directories. No hard-coded absolute paths exist.

**Context.** The CLI must produce identical behavior when cloned to any directory on any machine. Paths tied to a specific user's home directory or a specific checkout location break reproducibility.

**Consequences.** Clones behave consistently regardless of install location. Override `TAVILY_CLI_OUTPUT_DIR` when jobs need isolated output directories (e.g., cron tasks writing to per-dataset paths). The default `./tmp/tavily/` is gitignored, so result artifacts don't leak into commits.

## 5. Subcommands over unified `--mode`

**Decision.** `search` and `extract` are distinct argparse subparsers, not a single parser with a `--mode` flag.

**Context.** The two commands accept different arguments. `search` takes a natural-language query string as its positional argument, plus domain filters and time ranges. `extract` takes one or more URLs as positional arguments, plus extraction depth and chunking parameters. Merging both behind a unified parser forces every argument to be optional (because some don't apply to both modes), which weakens validation.

**What was rejected.** A single entry point like `python -m tavily_skill --mode search "query"` or `python -m tavily_skill --mode extract url1 url2`. This would require manual cross-validation of conflicting flags and produce less readable help output.

**Consequences.** Each subcommand has its own help text and its own argument namespace. Validation is scoped per-command. Adding a third subcommand (e.g., `crawl`) requires adding a new subparser and a new `_build_*_request` / `_normalize_*_response` pair, but does not perturb existing commands.

## 6. Protocol-based client for offline testing

**Decision.** The `SearchClient` is defined as a `Protocol` (structural typing), not an imported class. The `_build_client()` function does the actual `from tavily import TavilyClient` import at runtime.

**Context.** Unit tests must run without network access and without installing the `tavily-python` package. If the CLI module imported `TavilyClient` at the top level, importing the module would fail when `tavily` is absent — making the test suite dependent on the production dependency.

**What was rejected.** A top-level `from tavily import TavilyClient` — couples the module to the dependency at import time.

**Consequences.** Tests inject `StubClient` instances directly into `run_search()` and `run_extract()`. The protocol ensures type safety without runtime coupling. The production import path (`__import__("tavily")`) is the only place that references the actual SDK; if the SDK changes its API, only `_build_client()` needs updating.

## 7. Validation before API call

**Decision.** All argument validation runs before the Tavily client is even constructed. The `_validate_args()` function checks mutual exclusion, range constraints, and dependency rules, and calls `parser.error()` (which prints to stderr and exits) on failure.

**Context.** Tavily's API charges per call. A request with `--time-range week --start-date 2026-03-01` would either be rejected by the API with an opaque error, or silently accepted with undefined behavior. Either outcome costs credits and produces confusing error messages.

**Consequences.** Malformed requests never reach Tavily's servers. The error messages are argparse-native and reference the specific flags that conflict, rather than relaying an HTTP status code. The tradeoff is that validation logic must stay in sync with Tavily's API constraints — if the API relaxes a constraint (e.g., allows `max_results` above 20), the CLI won't reflect that until the validation is updated.

## 8. Single-file implementation

**Decision.** The entire CLI lives in `src/tavily_skill/cli.py`. There is no separate module for argument parsing, output dispatch, or response normalization.

**Context.** The surface area is small: three commands (`usage` has no request builder), two request builders, two response normalizers, one output dispatcher, one credential resolver. Splitting these into modules would create import graphs with one import per file — `from .args import build_parser`, `from .output import emit_payload`, `from .auth import get_api_key` — where each module is 30-80 lines. The indirection cost (jumping between files to trace a call path) outweighs any organizational benefit.

**What was rejected.** A multi-module structure with `cli/parser.py`, `cli/auth.py`, `cli/normalize.py`, `cli/output.py`. This is the correct structure for a project where each module does distinct, substantial work. Here, the work is tightly coupled: response normalization needs access to argument namespaces, output dispatch needs access to normalized payloads. Keeping them together makes the data flow visible in a single scroll.

**Consequences.** The file is long but linear. A reader can follow the entire call path — `main()` → `_validate_args()` → `_get_api_key()` → `_build_client()` → `run_search()` → `_normalize_search_response()` → `_emit_payload()` — without switching files. If the CLI grows to support `crawl` or `map`, the file should be split before adding a second command group. The threshold for splitting is roughly when any function needs to be imported from a test that isn't testing the CLI entry point.

## 9. Exclude Tavily's generated answer

**Decision.** The CLI always sends `include_answer=False`, provides no flag to enable Tavily's LLM-generated answer, and omits any answer returned by the upstream API from normalized output.

**Context.** Tavily's aggregated answer is a convenience feature for human-facing applications. For agent workflows, it is the wrong default: the answer is a lossy summary produced by a model the agent doesn't control, and treating it as a primary information source introduces a second layer of hallucination risk on top of the source content. Agents perform better when they read the raw results and synthesize their own conclusions.

**Consequences.** Search requests do not spend credits on answer generation, and agents cannot consume the generated answer through the CLI's payload or schema. The `include_answer` parameter remains explicit in every SDK request so this behavior cannot depend on upstream defaults.

## 10. `usage` bypasses the SDK and calls the REST endpoint directly

**Decision.** The `usage` subcommand calls `GET https://api.tavily.com/usage` with `urllib.request` and the resolved API key, rather than going through `TavilyClient`. It reuses the same credential chain, envelope, file-first output, and validation-before-call rules as the other subcommands.

**Context.** Tavily's usage/plan endpoint is not exposed by the Python SDK. The credit-consumption data is account-level metadata, distinct from the content endpoints, but agents that budget their own search spend need it in the same machine-readable shape as everything else.

**What was rejected.** Shelling out to `curl` (adds an external dependency and breaks the single-interpreter contract), and leaving usage out entirely (operators would keep re-deriving it ad hoc).

**Consequences.** The CLI gains a third subcommand with no new runtime dependency; `_fetch_usage` is the only place that talks to a non-content endpoint, and it is a plain GET whose JSON maps onto the existing `{command, input, data}` envelope. `data.remaining_credits` is computed client-side because the upstream `limit` field is `null`; `plan_usage`/`plan_limit` are the authoritative pair.

## 11. Batch search over a repeatable `--query`, one file per query

**Decision.** `search` accepts a repeatable `--query` flag. One or more `--query` values switch it into batch mode: the process runs every query internally and prints a single batch status envelope. The positional `query` argument becomes optional (`nargs="?"`) but keeps positional single-query file-mode behavior unchanged. Positional query and `--query` are mutually exclusive, as is passing neither. `--output` is rejected in batch mode. `--stdout` is not a search flag.

**Context.** An agent that needs ten independent searches previously paid ten model round-trips to invoke the CLI ten times, even though the searches themselves are independent HTTP calls. The round-trips, not the API latency, dominated the cost. Collapsing them into one process removes the round-trips while preserving the `{command, input, data}` file payload for each query.

**What was rejected.**
- A new `batch` subcommand. It would duplicate every search flag and split the search argument surface into two parsers that drift.
- A comma- or newline-delimited single `--query` string. Splitting on delimiter characters silently mangles legitimate multi-word queries and forces escaping rules on callers.
- Inlining all batch results into one stdout object. That reintroduces exactly the context-window blowup the file-first design exists to prevent, and breaks the "one query = one file" corpus invariant.

**Consequences.** Parallelism uses `concurrent.futures.ThreadPoolExecutor` from the standard library, defaulting to `--concurrency 4` with `--serial` forcing sequential execution. A single client instance is shared across worker threads, which is safe only while the Tavily SDK stays effectively stateless over HTTP; if a future SDK version keeps non-thread-safe state, the fallback is to build one client per call. Output paths are reserved on the main thread before dispatch, so concurrent workers never race on filename allocation and colliding auto-names get a numeric suffix. Per-query failures are isolated: a partial failure returns exit 0 with the error recorded in the envelope entry and a stderr warning, and only an all-queries failure returns exit 1, consistent with the existing single-query exit-code scheme. Usage errors still exit 2 through argparse. The batch envelope reuses the single-mode `output_mode` key (`"batch"` instead of `"file"`), nests counts under `summary` (`query_count`/`success_count`/`failed_count`/`credits_used`), and mirrors the sibling `firecrawl-skill` top-level shape so cross-repo consumers can share one parser.
