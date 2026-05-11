# Tavily Skill — Architecture Decisions

Each section records a design decision embodied in the codebase, with the context that motivated it, the alternatives considered, and the consequences of the choice.

## 1. Stable envelope over raw SDK passthrough

**Decision.** All responses are wrapped in `{command, input, data}` before reaching stdout or the output file. The envelope fields are hand-picked; they do not mirror the raw SDK dictionary.

**Context.** The Tavily Python SDK can change its response shape across versions — rename fields, restructure nested objects, add or remove optional keys. If agents embed parsing logic that depends on a particular SDK version's return shape, a version bump breaks them silently.

**What was rejected.** Passing the SDK response through unchanged, relying on documentation or convention to keep agents in sync with the SDK version.

**Consequences.** Downstream parsers see a stable surface regardless of SDK version. The cost is that new SDK fields don't automatically appear in the envelope; they must be explicitly added to the normalization functions. This is deliberate — it makes SDK upgrades an explicit, reviewable change rather than a silent surface expansion.

## 2. File-first output, stdout opt-in

**Decision.** Default behavior writes the full JSON payload to `./tmp/tavily/` and prints a compact status object to stdout. `--stdout` is required to print the full payload inline.

**Context.** In agent orchestration loops, subprocess stdout may be captured and forwarded into subsequent LLM calls. A search for "latest AI developments" can return hundreds of kilobytes of markdown content. If that payload lands in the agent's context window on every iteration — especially in a loop — it wastes tokens and dilutes signal.

**What was rejected.** Stdout-first output (print full results inline by default), with an optional `--output` flag for file persistence. This is the more human-friendly default, but humans are the secondary audience.

**Consequences.** Agents parsing subprocess output always receive a predictable, small status JSON. They extract the file path from `status.output_path` and read the full payload only when they need the content. The tradeoff is that a human running `python -m tavily_skill search "foo"` sees status metadata rather than results, until they learn to add `--stdout`. The status object includes `payload_schema` so callers know the data shape before opening the file.

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

**Context.** The two commands accept different arguments. `search` takes a natural-language query string as its positional argument, plus domain filters, time ranges, and answer mode. `extract` takes one or more URLs as positional arguments, plus extraction depth and chunking parameters. Merging both behind a unified parser forces every argument to be optional (because some don't apply to both modes), which weakens validation.

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

**Decision.** The entire CLI lives in `src/tavily_skill/cli.py` (560 lines). There is no separate module for argument parsing, output dispatch, or response normalization.

**Context.** The surface area is small: two commands, two request builders, two response normalizers, one output dispatcher, one credential resolver. Splitting these into modules would create import graphs with one import per file — `from .args import build_parser`, `from .output import emit_payload`, `from .auth import get_api_key` — where each module is 30-80 lines. The indirection cost (jumping between files to trace a call path) outweighs any organizational benefit.

**What was rejected.** A multi-module structure with `cli/parser.py`, `cli/auth.py`, `cli/normalize.py`, `cli/output.py`. This is the correct structure for a project where each module does distinct, substantial work. Here, the work is tightly coupled: response normalization needs access to argument namespaces, output dispatch needs access to normalized payloads. Keeping them together makes the data flow visible in a single scroll.

**Consequences.** The file is long but linear. A reader can follow the entire call path — `main()` → `_validate_args()` → `_get_api_key()` → `_build_client()` → `run_search()` → `_normalize_search_response()` → `_emit_payload()` — without switching files. If the CLI grows to support `crawl` or `map`, the file should be split before adding a second command group. The threshold for splitting is roughly when any function needs to be imported from a test that isn't testing the CLI entry point.

## 9. `answer=off` as the default

**Decision.** Tavily's LLM-generated answer is disabled by default (`answer="off"`). The caller must pass `--answer basic` or `--answer advanced` to receive it.

**Context.** Tavily's aggregated answer is a convenience feature for human-facing applications. For agent workflows, it is the wrong default: the answer is a lossy summary produced by a model the agent doesn't control, and treating it as a primary information source introduces a second layer of hallucination risk on top of the source content. Agents perform better when they read the raw results and synthesize their own conclusions.

**Consequences.** The `data.answer` field is `null` by default. Agents that want a summary can request it, but the default steers them toward the raw content. The `include_answer` parameter in the SDK call is set to `False` (not omitted) when answer is `"off"`, to make the intent explicit in the request.
