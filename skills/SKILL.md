---
name: tavily-skill
description: >-
  Runs Tavily-backed web search and URL extraction via python -m tavily_skill with stable JSON envelopes.
  Use when agents need terminal Tavily access, reproducible defaults (advanced depth, answers off), or file-oriented payloads outside MCP.
disable-model-invocation: true
---

# Tavily Skill

## When to use

- Terminal-first automation (cron, CI, Claude Code shell loops) needs Tavily search/extract with deterministic JSON.
- MCP Tavily tools are unavailable but Python + API keys exist on the host.
- Prefer compact stdout traffic: default mode persists bulky payloads under `./tmp/tavily/` unless `--stdout` is passed.

## Prerequisites

From **this repository root** (relative paths only):

```bash
uv pip install -e '.[dev]'
export TAVILY_API_KEY=tvly-...
```

Optional `ONEPASSWORD_TAVILY_REFERENCE` instead of exporting plaintext keys when `op` CLI is configured.

## Commands

```bash
python -m tavily_skill search "<query>"
python -m tavily_skill search "<query>" --stdout
python -m tavily_skill extract https://example.com/article
python -m tavily_skill extract URL --query "anchor phrase" --chunks-per-source 3 --stdout
```

## Defaults worth remembering

- `search_depth=advanced`, `max_results=6`, Tavily aggregated `--answer off`.
- Raw markdown snippets enabled unless `--raw-content off`.
- Images off unless `--images`.

## Safety

Treat Tavily answers (`--answer basic|advanced`) as hints only — synthesize conclusions from `data.results` / extracted chunks.

## More detail

- Operator-facing docs: `README.md`, `docs/prd.md`, `docs/rfc.md`.
