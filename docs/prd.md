# Tavily Skill — Product Requirements

## Overview

Tavily Skill is a small Python CLI (`python -m tavily_skill`, optional console script `tavily-skill`) that wraps the official Tavily Python SDK for **web search** and **URL content extraction**. It targets autonomous agents and shell pipelines first; humans are secondary.

## Problem

Direct Tavily usage from ad hoc snippets splits defaults across prompts (depth, answer mode, output shape). That yields brittle automation and wastes context when large JSON payloads bounce through stdout unnecessarily.

## Goals

1. **Single stable CLI surface** for the subset of Tavily features agents rely on most: `search` and `extract`.
2. **Predictable defaults** aligned with agentic research: `search_depth=advanced`, `max_results=6`, Tavily aggregated answers **off** by default (agents read citations instead).
3. **Structured JSON envelope**: each successful payload includes `command`, `input`, and `data` fields independent from raw SDK layout drift.
4. **Dual stdout semantics**: default mode writes full JSON to disk under `./tmp/tavily/` (override via `TAVILY_CLI_OUTPUT_DIR`) and prints a compact status object on stdout; `--stdout` streams the entire payload on stdout for one-shot tooling.

## Non-goals

- Parity with Tavily official CLI (`tvly`), MCP servers, or every SDK knob on day one.
- Offline caching, distributed crawling orchestration, or billing dashboards inside this repo.

## Authentication

Primary mechanism is **`TAVILY_API_KEY`** in the environment (optionally loaded via `--env-file` / `.env` discovery upward from cwd).

Optional: **`ONEPASSWORD_TAVILY_REFERENCE`** (alias **`OP_READ_TAVILY_KEY`**) pointing at any secret readable via `op read <reference>` so operators using the 1Password CLI avoid exporting plaintext keys. No vault/item identifiers ship with this codebase.

## Success Criteria

- `pytest tests/` passes offline without keys or network.
- Agents can parse `--json`-adjacent behavior (`--stdout`) deterministically from subprocess stdout.
- Documentation describes envelope schema and exit semantics explicitly enough that downstream prompts rarely reinvent wrappers.

## Release Constraints

Repository contents must remain suitable for **public Git hosting**: no personal vault paths, no workspace-local absolute directories in runtime defaults beyond cwd-relative `./tmp/tavily`.
