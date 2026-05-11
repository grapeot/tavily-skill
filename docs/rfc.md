# Tavily Skill — RFC

## Context

Agents orchestrated from Cursor, Claude Code, cron jobs, or CI often need Tavily-backed grounding. MCP integrations solve IDE-hosted workflows; this CLI solves **terminal-first automation** where MCP wiring is unavailable or undesirable.

## Design Decisions

### Stable envelope vs raw SDK passthrough

Responses normalize into `{ command, input, data }`. The envelope survives Tavily SDK field churn better than agents embedding undocumented dictionaries.

### Default persistence vs `--stdout`

Default artifact persistence minimizes accidental stuffing of megabyte-scale payloads back into LLM context windows during scripted loops. `--stdout` stays explicit for `jq` and ephemeral tooling.

### Optional 1Password bridge without bundled vault identifiers

Earlier iterations referenced concrete `op://` vault/item pairs suited to a private workspace. Public tooling removes baked paths entirely:

1. Prefer explicit `TAVILY_API_KEY`.
2. If missing, evaluate `_ONEPASSWORD_REF_ENV` / `_LEGACY_ONEPASSWORD_REF_ENV` and invoke `op read` against **that operator-supplied reference only**.

This keeps CI reproducible (inject secrets directly) while preserving ergonomics for 1Password users.

### Working-directory-relative artifact roots

Default outputs anchor under `Path.cwd() / "tmp" / "tavily"` so clones behave consistently regardless of install location. `TAVILY_CLI_OUTPUT_DIR` overrides when cron isolates jobs per dataset.

### Subcommands vs unified `--mode`

`search` and `extract` stay distinct argparse subcommands because inputs diverge (natural-language query vs URL lists). Mixing both behind generic flags raises validation complexity and hurts readability.

## Migration / Compatibility

Inside `knowledge_working`, `tools/tavily_cli.py` remains a thin shim that prepends `adhoc_jobs/tavily_skill_public/src` to `PYTHONPATH` and delegates to `tavily_skill.cli.main`. Legacy cron snippets invoking `python tools/tavily_cli.py …` continue to operate without edits while canonical sources live under `adhoc_jobs/tavily_skill_public`.

Existing automation that depended on implicit `op read` targets baked into older forks **must** set either:

- `TAVILY_API_KEY`, or
- `ONEPASSWORD_TAVILY_REFERENCE` / `OP_READ_TAVILY_KEY` with whatever vault/item paths your operator trusts — values stay outside git history.

## Out of Scope (near-term)

- Wrapping `crawl`, `map`, or Tavily Research endpoints — revisit once envelopes stabilize.

## Risks

- **Quota Burn**: integration tests gate behind `RUN_TAVILY_INTEGRATION=1`.
- **SDK breakage**: pin semver ranges conservatively in `pyproject.toml`; upgrade deliberately after changelog review.
