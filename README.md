# Tavily Skill

Small CLI around the [Tavily Python SDK](https://pypi.org/project/tavily-python/) for agent workflows: **`search`** and **`extract`**, stable JSON envelopes, predictable defaults.

## Quick start

```bash
cd adhoc_jobs/tavily_skill   # or your clone root
uv venv .venv
uv pip install -e '.[dev]'
export TAVILY_API_KEY=tvly-...
python -m tavily_skill search "latest developments in MCP"
python -m tavily_skill search "topic" --stdout | jq '.data.results[0].url'
```

Default behavior writes full payloads under `./tmp/tavily/` and prints a compact status JSON on stdout. Override the directory with `TAVILY_CLI_OUTPUT_DIR`.

### Optional 1Password CLI

```bash
export ONEPASSWORD_TAVILY_REFERENCE='op://Vault/Item/tavily_api_key'
python -m tavily_skill search "hello world"
```

Alias: `OP_READ_TAVILY_KEY`. Never commit vault references that expose private infrastructure.

## Documentation

- [`docs/prd.md`](docs/prd.md) — product intent and success criteria
- [`docs/rfc.md`](docs/rfc.md) — architecture decisions and migration notes
- [`docs/test.md`](docs/test.md) — how to run unit vs integration tests
- [`docs/public_release_review.md`](docs/public_release_review.md) — OSS hygiene checklist

## Cursor / Agent skill

See [`skills/SKILL.md`](skills/SKILL.md) for progressive-disclosure instructions tailored to autonomous agents.

## Development

```bash
uv run pytest tests/ -v
RUN_TAVILY_INTEGRATION=1 TAVILY_API_KEY=tvly-... uv run pytest tests/ -v -m integration
```

## Relationship to others

- Official Tavily CLI (`tvly`) ships separately from Tavily; this project optimizes for JSON envelopes + subprocess ergonomics in automation stacks.
- MCP integrations remain ideal for IDE-hosted agents; this CLI targets terminals and cron-style runners.
