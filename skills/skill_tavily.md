---
name: tavily-skill
description: >-
  Runs Tavily-backed web search and URL extraction via python -m tavily_skill with stable JSON envelopes.
  Use when agents need terminal Tavily access, reproducible defaults (advanced depth, answers off), or file-oriented payloads outside MCP.
disable-model-invocation: true
---

# Tavily Skill

Real-time web search and URL content extraction through the Tavily Python SDK. The CLI defaults to writing full payloads to local JSON files and returning a lightweight status object on stdout; use `--stdout` when you need the complete JSON inline.

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

## Usage

### Basic search

```bash
python -m tavily_skill search "latest AI news"
```

Defaults request `raw_content="markdown"` and writes the complete result to an auto-named file under `tmp/tavily/`; stdout returns only a status JSON.

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
- `answer="off"`
- `raw_content="markdown"`
- `include_images` disabled by default
- `include_image_descriptions` disabled by default
- If using 1Password: set `ONEPASSWORD_TAVILY_REFERENCE` to point at the credential field
- Default mode writes the complete result to an auto-named file under `tmp/tavily/`; stdout prints a lightweight status object with `payload_schema`, and hints go to stderr
- With `--output`, the complete result writes to the specified file; stdout still prints the lightweight status object with `payload_schema`
- With `--stdout`, the complete payload prints directly to stdout without writing to disk

## Parameter reference

### `search`

| Parameter | Description | Default |
|---|---|---|
| `query` | Search query | required |
| `--max-results` | Number of results, range 1–20 | `6` |
| `--search-depth` | `basic` / `advanced` / `fast` / `ultra-fast` | `advanced` |
| `--topic` | `general` / `news` / `finance` | `general` |
| `--time-range` | `day` / `week` / `month` / `year` | — |
| `--start-date` | Start date, `YYYY-MM-DD` | — |
| `--end-date` | End date, `YYYY-MM-DD` | — |
| `--include-domain` | Restrict to a domain; repeat for multiple | — |
| `--exclude-domain` | Exclude a domain; repeat for multiple | — |
| `--answer` | `off` / `basic` / `advanced` | `off` |
| `--stdout` | Print full payload directly to stdout | `False` |
| `--raw-content` | `off` / `markdown` / `text` | `markdown` |
| `--country` | Boost results by country | — |
| `--timeout` | Request timeout in seconds | `60` |
| `--images` | Enable image results | `False` |
| `--image-descriptions` | Include LLM-generated image descriptions; if `--images` is not explicitly passed, the CLI auto-enables image results | `False` |
| `--no-images` | Disable image results | `False` |
| `--no-image-descriptions` | Return image URLs without descriptions | `False` |
| `--output` | Write full result to a named JSON file; stdout still returns status schema | auto-writes to `tmp/tavily/` |

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
| `--output` | Write full result to a named JSON file; stdout still returns status schema | auto-writes to `tmp/tavily/` |

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
    "answer": null,
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

In default mode, `search`'s `data.results` retains the result items returned by Tavily, which should include `raw_content`. `data.answer` is `null` by default — it only contains a value when `--answer basic` or `--answer advanced` is explicitly passed, which requests Tavily's LLM-aggregated answer. When image descriptions are enabled, `data.images` is an array of objects containing `url` and `description`. For `extract`, `data.results` holds the URL extraction results and additionally carries `failed_results` and `failed_count`.

In default mode, stdout does not return this full payload. It returns a lightweight object containing the output path, summary information, and payload schema. The full payload only prints to stdout when `--stdout` is passed.

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
- `--chunks-per-source` requires `--query`
- The currently stable commands are `search` and `extract`
- `--output` still produces JSON on stdout, but that stdout is the status schema, not the full search result

## Operational guidance

- When running the Tavily CLI inside this workspace, prefer `./.venv/bin/python -m tavily_skill ...`. Do not assume a system `python` is available on PATH.
- If you want to consume results directly in the current turn rather than writing to disk first, pass `--stdout`. Otherwise stdout only returns a lightweight status object, and the full payload lands under `tmp/tavily/`.
- Do not rely on Tavily's LLM-aggregated answer for factual judgments. It can serve as a low-confidence hint, but never as a conclusion source. Default to `--answer off`.
- For routine research, default to `--raw-content markdown`. Base judgments on `data.results[*].raw_content`, source URLs, page titles, snippet content, and — when needed — content pulled via `extract`.
- Only pass `--raw-content off` when payload size is a confirmed bottleneck. Doing so means you must open the original links or continue with `extract` — don't rely solely on snippets and `data.answer`.

## More detail

- Operator-facing docs: `README.md`, `docs/prd.md`, `docs/rfc.md`
