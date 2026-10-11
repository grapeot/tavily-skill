# Tavily Skill — Product Description

## What this is

Tavily Skill is a Python CLI that wraps the Tavily web search API for autonomous agents and shell pipelines. It provides three subcommands — `search`, `extract`, and `usage` — and normalizes all responses into a stable JSON envelope that downstream parsers can depend on regardless of SDK version drift. `search` runs a single query by default and switches to batch mode when given one or more repeatable `--query` values, so an agent can launch many independent searches in one process instead of paying one model round-trip per invocation.

The CLI is not a general-purpose replacement for Tavily's official tooling. It is purpose-built for a specific environment: an agent orchestration loop where Python is available, the caller is another program (not a human reading terminal output), and the cost of accidentally stuffing a megabyte-scale payload into an LLM context window is real.

## Why it exists

Calling the Tavily SDK directly from ad hoc scripts creates three recurring problems in agent workflows.

**Context window waste.** The default human-readable output from most API wrappers sends full JSON bodies to stdout, and agents or shell scripts that don't redirect them end up embedding entire search result payloads into subsequent calls. In a loop, this compounds fast.

**Interface drift.** Raw SDK responses change shape across versions — fields get renamed, nested objects restructure, optional keys appear and disappear. Every downstream parser that reads `response["results"]` directly has to track these changes. When an agent's prompt embeds parsing logic that assumes a particular SDK return shape, a minor version bump breaks it silently.

**Credential sprawl.** Ad hoc scripts tend to accumulate hard-coded API key references, `.env` paths tied to a specific machine, or 1Password vault paths that leak internal infrastructure layout into committed code.

Tavily Skill solves each of these at the architectural level — not through convention or documentation, but through structural defaults that make the right thing the easy thing.

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Agent / cron / shell pipeline                   │
│  python -m tavily_skill search "query"           │
└──────────────────┬───────────────────────────────┘
                   │
     ┌─────────────▼──────────────┐
     │  argparse + validation      │
     │  (mutual exclusion, range,  │
     │   dependency checks)        │
     └─────────────┬──────────────┘
                   │
     ┌─────────────▼──────────────┐
     │  Credential resolution      │
     │  TAVILY_API_KEY             │
     │  → 1Password reference     │
     │  → RuntimeError             │
     └─────────────┬──────────────┘
                   │
     ┌─────────────▼──────────────┐
     │  TavilyClient (SDK)         │
     │  search() / extract()       │
     └─────────────┬──────────────┘
                   │
     ┌─────────────▼──────────────┐
     │  Normalize → {command,     │
     │  input, data} envelope     │
     └─────────────┬──────────────┘
                   │
           ┌────────▼────────┐
           │  Output dispatch  │
           │  ┌──────────────┐ │
           │  │ File mode    │ │
           │  │ full → disk  │ │
           │  │ status →     │ │
           │  │ stdout       │ │
           │  └──────────────┘ │
           └──────────────────┘
```

### The envelope

Every response, regardless of command, follows this structure:

```json
{
  "command": "search",
  "input": { /* all args as passed */ },
  "data": {
    "result_count": 0,
    "image_count": 0,
    "results": [],
    /* command-specific fields */
  }
}
```

The `command` and `data` fields are the stable contract. Whatever the Tavily SDK returns internally — renamed keys, restructured nested objects — the envelope surface remains constant. Downstream code parses `data.result_count`, not `response["results"].length` or whatever the raw SDK happens to return. When the SDK adds new fields, the envelope grows; existing fields do not change type or disappear.

The `input` field captures the exact arguments the caller passed. This is not decoration — it makes every payload a self-contained record. An agent that receives a stale result file can reconstruct what query produced it without consulting external state.

### Output semantics

File mode is the only success path for `search` and `extract`. Full results are always written to disk and are never inlined on stdout. `usage --stdout` remains the exception and may inline its small usage payload.

**File mode.** The full normalized JSON payload `{command, input, data}` (which retains result items and raw content bodies rather than every raw SDK key) writes to an auto-named file under `TAVILY_CLI_OUTPUT_DIR` if set, otherwise `./tmp/tavily/<command>_<timestamp>_<slug>.json`. An explicit `--output` path overrides both default and environment directories, writing directly to the specified path without guaranteeing shared corpus coverage.

The CLI prints a compact status object to stdout — `{command, status, output_mode, output_path, payload_bytes, summary, payload_schema}` — and a one-line confirmation to stderr. `summary` provides `result_count`, `failed_count` (`null` for search), and `image_count`.

Callers must follow an exit-before-parse and exact-path contract:
1. Verify `proc.returncode == 0` before calling `json.loads(proc.stdout)`. Nonzero exits (exit 2 for invalid flags like removed `--stdout`, exit 1 for API/write failures) must be handled via stderr, not blindly parsed as status JSON.
2. Open the exact `output_path` returned in that invocation's status envelope, avoiding globbing or newest-mtime heuristics. In batch mode, only open entries with `error is None` and a nonempty `output_path`.
3. Select only necessary bounded fields in code (for example, top N results and truncated text excerpts). Mandatory file output keeps result bodies off stdout, but does not automatically keep results out of LLM context if callers dump entire files into prompts.

See the [single-search Python example](../skills/skill_tavily.md#reading-search-results-safely-in-python-single-search) and [batch Python example](../skills/skill_tavily.md#reading-batch-search-results-safely-in-python) for executable implementations.

**Batch mode (`--query` repeated).** Each `--query` value is one complete query. The process runs them with a thread pool (default concurrency 4; `--serial` forces sequential) and writes one full payload file per query, preserving the "one query = one file" corpus invariant. Stdout receives exactly one lightweight batch status envelope, reusing `output_mode: "batch"` and nesting counts under `summary` (`query_count`, `success_count`, `failed_count`, `credits_used`), with one `{query, output_path, summary, error}` entry per query — never raw content. `input` echoes the effective parameters (including the effective `concurrency`), and `output_dir` reports where files landed. The top-level shape matches the sibling `firecrawl-skill` so agents can parse both with one code path. `--output` is rejected in batch mode, since per-query file naming is automatic; empty or whitespace-only queries are usage errors. A partial failure returns exit 0 with per-query errors in the envelope plus a stderr warning; if every query fails the process returns exit 1. The positional single-query form is unchanged and mutually exclusive with `--query`.

The key design choice makes file mode mandatory because the primary caller is an agent loop: callers read result files selectively in code. Explicit `--output` paths override environment and default directories; neither custom directory configuration nor explicit output guarantees canonical shared raw coverage.

### Credential resolution

The CLI resolves API keys through a chain, not a single env var check:

1. `TAVILY_API_KEY` — explicit, works everywhere
2. `ONEPASSWORD_TAVILY_REFERENCE` → `op read <reference>` — for operators who use 1Password CLI
3. `RuntimeError` with a message that tells the operator exactly which env vars to set

This chain matters for open-source distribution. The code never contains a vault path, a vault UUID, or an item name. The operator provides their own reference string — `op://Personal/MyTavily/credential` or whatever their vault layout happens to be — and the CLI resolves it at runtime. CI environments skip the 1Password path entirely and inject `TAVILY_API_KEY` directly.

### Path conventions

Every path the CLI generates is relative to the current working directory:

- Default output: `./tmp/tavily/` (overridable via `TAVILY_CLI_OUTPUT_DIR`)
- `.env` discovery: walks upward from CWD, checking each parent directory for `.env`
- Auto-generated filenames: `search_20260510_143022_latest_ai.json` — timestamped and slugified for sortability

No hard-coded absolute paths exist in the codebase. A clone on any machine, in any directory, produces the same behavior.

### Validation at the boundary

All argument validation happens before any API call. The parser enforces:

- Mutual exclusion: `--time-range` vs `--start-date`/`--end-date`; `usage` still rejects combining `--stdout` and `--output`. Usage errors, including unrecognized `--stdout` on `search` and `extract`, happen before any API call
- Mode selection on `search`: positional `query` vs `--query`, both present or neither present is an error; batch mode rejects `--output`
- Range: `max_results` between 1 and 20, `timeout` > 0, `concurrency` >= 1
- Dependency: `--chunks-per-source` requires `--query` on `extract`
- Implicit enable: `--image-descriptions` implicitly enables `--images` (because descriptions without images don't make API sense)

This is not cosmetic. Every validation error that would surface as a cryptic HTTP 400 from Tavily's API instead surfaces as a clear argparse error before the call is made. The caller never pays for a malformed request.

## What is deliberately excluded

The CLI covers the subset of Tavily features that agents use in practice: `search`, `extract`, and `usage`. It does not wrap `crawl`, `map`, or Tavily Research endpoints. These endpoints have different response shapes, different pagination semantics, and different error modes. Adding them would either require generalizing the envelope in ways that weaken the existing contract, or maintaining parallel envelope types that double the maintenance surface. Neither tradeoff is worth making until the additional endpoints are demonstrably needed in agent workflows.

`usage` is a read-only account query, not a billing dashboard: it reports the plan and credit counters that Tavily exposes at `GET /usage`. The CLI does not cache results or manage quotas — those remain orchestration-layer concerns.

## Defaults and their rationale

Every default is set to minimize surprise in agent workflows:

- `search_depth=advanced` — basic depth returns fewer results with less context, which agents handle worse
- `max_results=6` — enough to get signal across multiple sources, not so many that downstream processing becomes expensive
- `raw_content=markdown` — the structured content is what agents actually read; turning it off is an optimization, not the default
- `include_images=False` — most research workflows don't consume images; including them silently inflates payload size
- `topic=general` — the least presumptuous default; `news` and `finance` are domain-specific optimizations that callers opt into
- `concurrency=4` in batch mode — enough overlap to hide network latency without flooding the API or the local thread pool; `--serial` is available when determinism or rate limits matter

## Testing strategy

The test suite is split into two tiers with a hard gate between them.

Unit tests (always run) exercise argument parsing, request construction, response normalization, and output dispatch. They use a `StubClient` that records calls and returns fake responses. No network, no API key.

Integration tests (5 tests, gated behind `RUN_TAVILY_INTEGRATION=1`) run real subprocess invocations against the live Tavily API. They verify end-to-end behavior: credential resolution through both env var and 1Password paths, output file creation, status JSON structure, and the guarantee that raw content never appears on stdout in default mode.

This separation matters because integration tests consume Tavily credits. The gate makes it impossible to accidentally run them during normal development.
