---
name: tavily-skill
description: >-
  Runs Tavily-backed web search and URL extraction via python -m tavily_skill with stable JSON envelopes.
  Use when agents need terminal Tavily access, reproducible defaults, or file-oriented payloads outside MCP.
disable-model-invocation: true
---

# Tavily Skill

Real-time web search and URL content extraction through the Tavily Python SDK. The CLI defaults to writing full payloads to local JSON files and returning a lightweight status object on stdout; use `--stdout` when you need the complete JSON inline.

This skill and `firecrawl-skill` run in parallel. **Prefer `firecrawl-skill` for new search/extract tasks; use this skill for its unique capabilities (LLM image descriptions, chunked extraction with `--chunks-per-source`) or when Firecrawl is unavailable/out of credits.**

## When to use

Trigger when the user expresses any of these intents:

- Look up the latest information, news, or web content
- Search a topic and keep structured JSON results
- Need to limit result count, time range, or domain scope
- Need image results and image descriptions
- Already have a URL and want to extract its body content directly
- Any scenario suited for real-time web search via Tavily

## Prerequisites

- Entry point: `python -m tavily_skill` (after installing the package from this repository root)
- Python dependencies: `tavily-python`, `python-dotenv` (installed via `uv pip install -e '.[dev]'` in `.venv`)
- API key: `TAVILY_API_KEY` takes priority; optionally `ONEPASSWORD_TAVILY_REFERENCE` (value is an `op read`-compatible reference; never commit private vault paths to a public repository)

## First-time setup

On the first use in a workspace, check whether `TAVILY_CLI_OUTPUT_DIR` is set (in the repo's `.env` or the ambient environment). If it is not set, mention this to the user once during setup — not at runtime — and recommend pointing it at one dedicated, persistent directory (for example a knowledge-base `web_snapshots/raw/` folder). The default `./tmp/tavily/` is ephemeral and resolves relative to the current working directory, so payloads scatter across session directories and get cleaned up; a single stable directory lets every search/extract payload accumulate as a timestamped corpus of primary sources, which pays off over time for research, auditing, and later retrieval.

## Usage

### Basic search

```bash
python -m tavily_skill search "latest AI news"
```

Defaults request `raw_content="markdown"` and writes the complete result to an auto-named file under `tmp/tavily/` (or `TAVILY_CLI_OUTPUT_DIR` when set); stdout returns only a status JSON.

### Specify result count and time range

```bash
python -m tavily_skill search "openai releases" --max-results 10 --time-range month
```

### Restrict to specific domains

```bash
python -m tavily_skill search "agent framework" \
  --include-domain github.com \
  --include-domain docs.anthropic.com
```

### Batch several independent searches in one process

```bash
python -m tavily_skill search \
  --query "latest AI news" \
  --query "openai releases" \
  --query "anthropic news" \
  --concurrency 4
```

Each `--query` value is one complete query string (multi-word values are not split). The positional `query` form still works and is mutually exclusive with `--query`; passing both or neither is a usage error. Batch mode writes one auto-named file per query and prints exactly one batch status envelope to stdout; `--stdout` and `--output` are single-mode only. Add `--serial` (or `--concurrency 1`) to run sequentially; `--serial` wins over `--concurrency`.

### Write to a named file

```bash
python -m tavily_skill search "AI coding tools" --output /tmp/tavily_search.json
```

### Print full JSON directly to stdout

```bash
python -m tavily_skill search "AI coding tools" --stdout
```

### URL content extraction

```bash
python -m tavily_skill extract https://tavily.com
python -m tavily_skill extract https://tavily.com --query "agent search" --chunks-per-source 3 --output /tmp/tavily_extract.json
```

### Check credit usage

```bash
python -m tavily_skill usage --stdout
```

Reports the account plan, credits used this cycle, remaining credits (`plan_limit - plan_usage`), a per-endpoint breakdown, and the current key's own usage.

### Disable images or raw content

```bash
python -m tavily_skill search "earnings news" --stdout --no-images --raw-content off
```

### Explicitly enable images

```bash
python -m tavily_skill search "latest Apple event stage photos" --images
python -m tavily_skill search "latest Apple event stage photos" --images --image-descriptions
```

## Default behavior

- `search_depth="advanced"`
- `max_results=6`
- `topic="general"`
- `raw_content="markdown"`
- `include_images` disabled by default
- `include_image_descriptions` disabled by default
- If using 1Password: set `ONEPASSWORD_TAVILY_REFERENCE` to point at the credential field
- Default mode writes the complete result to an auto-named file under `tmp/tavily/` (or under `TAVILY_CLI_OUTPUT_DIR` when set); stdout prints a lightweight status object with `payload_schema`, and hints go to stderr
- With `--output`, the complete result writes to the specified file; stdout still prints the lightweight status object with `payload_schema`
- With `--stdout`, the complete payload prints directly to stdout without writing to disk
- With one or more `--query`, batch mode writes one auto-named file per query and prints exactly one batch status envelope to stdout (no raw content inline); `--output` and `--stdout` are rejected

## Parameter reference

### `search`

| Parameter | Description | Default |
|---|---|---|
| `query` | Search query (single mode; mutually exclusive with `--query`) | — |
| `--query` | Repeatable batch query; each value is a complete query string. Enables batch mode and is mutually exclusive with the positional `query` | — |
| `--concurrency` | Max parallel searches in batch mode | `4` |
| `--serial` | Force sequential batch execution; overrides `--concurrency` | `False` |
| `--max-results` | Number of results, range 1–20 | `6` |
| `--search-depth` | `basic` / `advanced` / `fast` / `ultra-fast` | `advanced` |
| `--topic` | `general` / `news` / `finance` | `general` |
| `--time-range` | `day` / `week` / `month` / `year` | — |
| `--start-date` | Start date, `YYYY-MM-DD` | — |
| `--end-date` | End date, `YYYY-MM-DD` | — |
| `--include-domain` | Restrict to a domain; repeat for multiple | — |
| `--exclude-domain` | Exclude a domain; repeat for multiple | — |
| `--stdout` | Print full payload directly to stdout | `False` |
| `--raw-content` | `off` / `markdown` / `text` | `markdown` |
| `--country` | Boost results by country | — |
| `--timeout` | Request timeout in seconds | `60` |
| `--images` | Enable image results | `False` |
| `--image-descriptions` | Include LLM-generated image descriptions; if `--images` is not explicitly passed, the CLI auto-enables image results | `False` |
| `--no-images` | Disable image results | `False` |
| `--no-image-descriptions` | Return image URLs without descriptions | `False` |
| `--output` | Write full result to a named JSON file; stdout still returns status schema | auto-writes to `tmp/tavily/` or `TAVILY_CLI_OUTPUT_DIR` |

### `extract`

| Parameter | Description | Default |
|---|---|---|
| `urls...` | One or more URLs, up to 20 | required |
| `--extract-depth` | `basic` / `advanced` | `advanced` |
| `--format` | `markdown` / `text` | `markdown` |
| `--query` | Keep only chunks relevant to the query | — |
| `--chunks-per-source` | Number of relevant chunks retained per URL | — |
| `--stdout` | Print full payload directly to stdout | `False` |
| `--images` | Enable image extraction | `False` |
| `--no-images` | Disable image extraction | `False` |
| `--favicon` | Return favicon URLs | `False` |
| `--timeout` | Request timeout in seconds | `60` |
| `--output` | Write full result to a named JSON file; stdout still returns status schema | auto-writes to `tmp/tavily/` or `TAVILY_CLI_OUTPUT_DIR` |

### `usage`

| Parameter | Description | Default |
|---|---|---|
| `--stdout` | Print full payload directly to stdout | `False` |
| `--output` | Write full usage payload to a named JSON file; stdout still returns status schema | auto-writes to `tmp/tavily/` or `TAVILY_CLI_OUTPUT_DIR` |
| `--timeout` | Request timeout in seconds | `60` |

`usage` calls `GET https://api.tavily.com/usage` directly (the Tavily SDK has no method for it) and normalizes the account/key usage into the standard envelope. `data.remaining_credits` is derived as `plan_limit - plan_usage` (`null` when either is missing).

## Image guidance

Images and image descriptions are off by default. The reason is not that images lack value — it's that most research and survey workflows don't consume `data.images`, and enabling them silently inflates payload size.

Enable explicitly in these scenarios:

- Writing an external report or newsletter that needs accompanying images
- The topic is inherently visual — UI, hardware appearance, satellite imagery, document samples, news event photos
- You explicitly need image search, not factual web retrieval

Recommended usage:

```bash
# Image URLs only
python -m tavily_skill search "topic" --images

# Image URLs with descriptions (useful for later manual filtering or captions)
python -m tavily_skill search "topic" --images --image-descriptions
```

Keep disabled in these scenarios:

- Routine fact-checking, news aggregation, product/company research
- Sub-agent research where token and output volume compression matters
- Downstream workflows that only consume URLs, text excerpts, and structured conclusions

## Output structure

The top-level structure is fixed:

```json
{
  "command": "search",
  "input": {},
  "data": {
    "query": "...",
    "results": [],
    "images": [],
    "response_time": 0.0,
    "request_id": "...",
    "usage": {},
    "result_count": 0,
    "image_count": 0
  }
}
```

In default mode, `search`'s `data.results` retains the result items returned by Tavily, which should include `raw_content`. When image descriptions are enabled, `data.images` is an array of objects containing `url` and `description`. For `extract`, `data.results` holds the URL extraction results and additionally carries `failed_results` and `failed_count`.

In default mode, stdout does not return this full payload. It returns a lightweight object containing the output path, summary information, and payload schema. The full payload only prints to stdout when `--stdout` is passed.

In batch mode, stdout returns exactly one batch status envelope whose top-level shape matches `firecrawl-skill`. Every entry follows the per-query schema `{"query", "output_path", "summary", "error"}`, where `summary` is `{"result_count", "image_count"}` and `error` is `null` or `{"http_status", "error"}`:

```json
{
  "command": "search",
  "status": "ok",
  "output_mode": "batch",
  "output_dir": "tmp/tavily",
  "input": {
    "queries": ["q1", "q2", "q3"],
    "concurrency": 4,
    "serial": false,
    "max_results": 6,
    "search_depth": "advanced",
    "topic": "general",
    "time_range": null,
    "start_date": null,
    "end_date": null,
    "include_domains": [],
    "exclude_domains": [],
    "include_images": false,
    "raw_content": "markdown",
    "country": null,
    "timeout": 60
  },
  "summary": {"query_count": 3, "success_count": 3, "failed_count": 0, "credits_used": null},
  "results": [
    {"query": "q1", "output_path": "...", "summary": {"result_count": 6, "image_count": 0}, "error": null}
  ],
  "payload_schema": {}
}
```

`status` is `ok` (all succeeded), `partial` (some failed), or `error` (all failed). `concurrency` is the effective value (1 when `--serial`); `credits_used` is always `null` because Tavily search does not report credits; a failed entry has `"error": {"http_status": null, "error": "<message>"}`. Partial failure returns exit 0 with a stderr warning; if every query fails the exit code is 1. Usage errors exit 2.

## Testing

Run unit tests only (default):

```bash
uv run pytest tests/ -v
```

Run paid integration tests explicitly:

```bash
RUN_TAVILY_INTEGRATION=1 TAVILY_API_KEY=tvly-... uv run pytest tests/ -v -m integration
```

Integration tests hit the real Tavily API. If `TAVILY_API_KEY` is not set, configure `ONEPASSWORD_TAVILY_REFERENCE` and ensure the local `op` CLI is available.

## Notes

- `--time-range` and `--start-date`/`--end-date` are mutually exclusive — use one or the other
- `--chunks-per-source` requires `--query` (the `extract` flag, not the `search` batch flag)
- The currently stable commands are `search`, `extract`, and `usage`
- `--output` still produces JSON on stdout, but that stdout is the status schema, not the full search result
- On `search`, the positional query and the repeatable `--query` are mutually exclusive; `--output` and `--stdout` are rejected in batch mode
- On `search`, a positional query keeps the existing single-file status contract; batch mode returns one envelope and writes one file per query

## Operational guidance

- Run the CLI from this skill repo's root directory using its project-local interpreter: `./.venv/bin/python -m tavily_skill ...`. Do not run it from a parent workspace root, because the parent environment may not load this repo's `.env`, so `ONEPASSWORD_TAVILY_REFERENCE` / `TAVILY_API_KEY` may be missing even though sub-agents or project-local calls work.
- If you want to consume results directly in the current turn rather than writing to disk first, pass `--stdout`. Otherwise stdout only returns a lightweight status object, and the full payload lands under `tmp/tavily/` (or `TAVILY_CLI_OUTPUT_DIR` when set).
- For routine research, default to `--raw-content markdown`. Base judgments on `data.results[*].raw_content`, source URLs, page titles, snippet content, and — when needed — content pulled via `extract`.
- Only pass `--raw-content off` when payload size is a confirmed bottleneck. Doing so means you must open the original links or continue with `extract` rather than relying solely on snippets.

## Speed optimization

When several queries are independent, do not spawn one CLI process per query. Pass them as repeatable `--query` flags so they run in a single process, one parallel wave:

```bash
python -m tavily_skill search --query "q1" --query "q2" --query "q3" --concurrency 4
```

Every standalone invocation re-pays fixed costs that have nothing to do with the search itself: Python process start, TLS connection setup, and credential resolution. If the key comes from `ONEPASSWORD_TAVILY_REFERENCE`, each call shells out to `op read`, which alone costs roughly 0.9s. With N queries that is N times the fixed cost plus N serial API waits; batch mode pays the fixed cost once and overlaps the waits.

The cheapest additional win is removing the `op read` step entirely. Put a raw `TAVILY_API_KEY=...` in the repository's local, gitignored `.env` so the CLI reads it directly and never invokes 1Password. Never commit that file or paste the key anywhere shared.

To quantify the gain on your own machine, run the opt-in benchmark at [`benchmarks/latency.py`](../benchmarks/latency.py) (set `RUN_TAVILY_LATENCY=1`; it spends real credits).

## More detail

- Operator-facing docs: `README.md`, `docs/prd.md`, `docs/rfc.md`
