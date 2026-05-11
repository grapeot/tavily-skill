# Tavily Skill — Product Description

## What this is

Tavily Skill is a Python CLI that wraps the Tavily web search API for autonomous agents and shell pipelines. It provides two subcommands — `search` and `extract` — and normalizes all responses into a stable JSON envelope that downstream parsers can depend on regardless of SDK version drift.

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
          │  │ File mode    │ │  default
          │  │ (default)    │ │
          │  │ full → disk  │ │
          │  │ status →     │ │
          │  │ stdout       │ │
          │  └──────────────┘ │
          │  ┌──────────────┐ │
          │  │ --stdout     │ │  opt-in
          │  │ full →       │ │
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

The CLI has two output modes, and the default is the one that protects LLM context windows.

**File mode (default).** The full JSON payload writes to `./tmp/tavily/<command>_<timestamp>_<slug>.json`. The CLI prints a compact status object to stdout — `{command, status, output_path, summary, payload_schema}` — and a one-line confirmation to stderr. An agent calling this from a subprocess reads the status from stdout, extracts the file path, and only reads the full payload when it actually needs the results. The status object includes `payload_schema`, so the agent knows the shape of the data before opening the file.

**Stdout mode (`--stdout`).** The full payload prints to stdout. No file is written. This mode exists for one-shot tooling — `jq` pipelines, ephemeral queries — where the caller explicitly opts into receiving the full body inline.

The key design choice: file mode is the default because the default caller is an agent loop, not a human. If a human wants inline output, they pass `--stdout`. The tradeoff is ergonomics for readability, and the CLI leans toward the former because readability is the agent's problem, not the tool's.

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

- Mutual exclusion: `--time-range` vs `--start-date`/`--end-date`, `--stdout` vs `--output`
- Range: `max_results` between 1 and 20, `timeout` > 0
- Dependency: `--chunks-per-source` requires `--query` on `extract`
- Implicit enable: `--image-descriptions` implicitly enables `--images` (because descriptions without images don't make API sense)

This is not cosmetic. Every validation error that would surface as a cryptic HTTP 400 from Tavily's API instead surfaces as a clear argparse error before the call is made. The caller never pays for a malformed request.

## What is deliberately excluded

The CLI covers the subset of Tavily features that agents use in practice: `search` and `extract`. It does not wrap `crawl`, `map`, or Tavily Research endpoints. These endpoints have different response shapes, different pagination semantics, and different error modes. Adding them would either require generalizing the envelope in ways that weaken the existing contract, or maintaining parallel envelope types that double the maintenance surface. Neither tradeoff is worth making until the additional endpoints are demonstrably needed in agent workflows.

The CLI does not cache results, manage API quotas, or provide billing dashboards. These are orchestration-layer concerns that belong in whatever system calls the CLI, not in the CLI itself.

## Defaults and their rationale

Every default is set to minimize surprise in agent workflows:

- `search_depth=advanced` — basic depth returns fewer results with less context, which agents handle worse
- `max_results=6` — enough to get signal across multiple sources, not so many that downstream processing becomes expensive
- `answer=off` — Tavily's LLM-generated answer is a low-confidence summary; agents should synthesize from raw results, not delegate reasoning
- `raw_content=markdown` — the structured content is what agents actually read; turning it off is an optimization, not the default
- `include_images=False` — most research workflows don't consume images; including them silently inflates payload size
- `topic=general` — the least presumptuous default; `news` and `finance` are domain-specific optimizations that callers opt into

## Testing strategy

The test suite is split into two tiers with a hard gate between them.

Unit tests (19 tests, always run) exercise argument parsing, request construction, response normalization, and output dispatch. They use a `StubClient` that records calls and returns fake responses. No network, no API key.

Integration tests (5 tests, gated behind `RUN_TAVILY_INTEGRATION=1`) run real subprocess invocations against the live Tavily API. They verify end-to-end behavior: credential resolution through both env var and 1Password paths, output file creation, status JSON structure, and the guarantee that raw content never appears on stdout in default mode.

This separation matters because integration tests consume Tavily credits. The gate makes it impossible to accidentally run them during normal development.
