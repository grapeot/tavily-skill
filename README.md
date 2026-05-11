# Tavily Skill

A CLI for AI agents to run Tavily web search and URL extraction. Not a human-facing tool — the output format, defaults, and subprocess contract are all designed for another program to parse.

## What this gives you

Two subcommands: `search` (web search with domain filters, time ranges, and image support) and `extract` (pull full-page content from URLs). All responses are normalized into a stable `{command, input, data}` JSON envelope that won't break when the Tavily SDK changes its response shape.

The default behavior writes the full payload to disk and returns a compact status JSON on stdout — so agents don't accidentally stuff megabyte-scale search results into their context windows unless they explicitly ask for them.

## Setting up for AI agents

This is a three-step setup. Step 1 is done by the human who operates the agent. Steps 2 and 3 configure the agent itself.

### Step 1: Install the package

```bash
git clone https://github.com/.../tavily-skill  # or your fork
cd tavily-skill
uv venv .venv
uv pip install -e '.[dev]'
```

Set your Tavily API key:

```bash
export TAVILY_API_KEY=tvly-...
```

If you use 1Password CLI, you can set `ONEPASSWORD_TAVILY_REFERENCE` to an `op read`-compatible secret reference instead of exporting the key directly. The CLI resolves it at runtime.

Verify it works:

```bash
python -m tavily_skill search "hello world" --stdout
```

The package is now available as `python -m tavily_skill` (or the console script `tavily-skill`) from this directory.

### Step 2: Give your agent the skill file

Copy [`skills/skill_tavily.md`](skills/skill_tavily.md) to wherever your agent looks for skill definitions. This depends on your setup:

- **Cursor / Claude Code**: place it in `.cursor/skills/` or `.claude/skills/` under your project root
- **Custom agent setups**: place it in whatever directory your agent's prompt references for skill loading

The skill file is a progressive-disclosure instruction set. It tells the agent:
- When to reach for Tavily (trigger phrases)
- What the CLI does and its defaults
- Full parameter reference tables for both `search` and `extract`
- Output structure schema
- Operational guidance (when to use `--stdout`, when to enable images, what not to trust)

### Step 3: Tell your agent to load the skill

Add a line to your agent's configuration file that tells it to read the skill when certain triggers appear. The exact mechanism depends on your agent:

**If your agent reads `AGENTS.md` or `CLAUDE.md`**, add a line like:

```markdown
- When the user asks to search the web, look up recent information, or extract content from a URL: read `skills/skill_tavily.md` and use `python -m tavily_skill` as documented there.
```

**If your agent supports YAML frontmatter skill routing**, the skill file already has `disable-model-invocation: true` set, so the agent reads it as a reference rather than invoking it directly.

After this setup, when a user says "search for the latest MCP developments," the agent knows to consult the skill file and run `python -m tavily_skill search "latest MCP developments"`.

## How the agent uses it

From the agent's perspective, the workflow is:

```bash
# Search with defaults (writes full payload to ./tmp/tavily/, returns status on stdout)
python -m tavily_skill search "latest AI news"

# Search with full output on stdout (for one-shot consumption)
python -m tavily_skill search "latest AI news" --stdout

# Extract full content from a URL
python -m tavily_skill extract https://example.com/article --stdout
```

In default mode, stdout returns a status object like:

```json
{
  "command": "search",
  "status": "ok",
  "output_mode": "file",
  "output_path": "tmp/tavily/search_20260510_143022_latest_ai_news.json",
  "summary": {"result_count": 6, "image_count": 0, "has_answer": false},
  "payload_schema": { ... }
}
```

The agent reads the `output_path` from the status and opens the file when it needs the actual results. The `payload_schema` field tells it the data shape before reading.

When the agent passes `--stdout`, it receives the full search payload directly and should consume it in the current turn (don't pipe it into another subprocess without serializing first).

Key defaults the agent should be aware of — they are optimized for agent workflows and differ from human-facing Tavily usage:

- `search_depth=advanced` — deeper, higher-quality results
- `max_results=6` — enough signal across diverse sources without overloading context
- `answer=off` — the agent synthesizes from raw content; Tavily's LLM-generated answer is a lossy summary
- `include_images=False` — most research workflows don't consume images; enable explicitly when needed
- `raw_content=markdown` — structured content that agents can actually parse

The full parameter reference is in [`skills/skill_tavily.md`](skills/skill_tavily.md).

## Developing

If you're contributing to the CLI itself:

```bash
git clone https://github.com/.../tavily-skill
cd tavily-skill
uv venv .venv
uv pip install -e '.[dev]'
```

Run the test suite:

```bash
uv run pytest tests/ -v                    # unit tests (no network, no API key)
RUN_TAVILY_INTEGRATION=1 TAVILY_API_KEY=tvly-... uv run pytest tests/ -v -m integration  # live API tests
```

Architecture and design rationale are documented in:

- [`docs/prd.md`](docs/prd.md) — what this is, why each design choice exists, system architecture
- [`docs/rfc.md`](docs/rfc.md) — catalog of architectural decisions with alternatives and consequences
- [`docs/test.md`](docs/test.md) — test strategy and how to run unit vs integration tests
