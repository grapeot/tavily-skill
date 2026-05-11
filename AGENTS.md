# AGENTS.md — Tavily Skill

## Layout

- `src/tavily_skill/` — Python package (`cli.py` owns argparse + Tavily calls).
- `tests/` — pytest suite (offline-first).
- `docs/` — PRD, RFC, testing notes, public-release checklist.
- `skills/` — Cursor-agent SKILL entrypoint (English).
- `scripts/run_cli.sh` — convenience runner once `.venv` exists.

Paths in docs commands assume **repository root** as cwd unless noted otherwise—avoid absolute filesystem prefixes.

## Expectations

1. After substantive edits, append a dated bullet under `docs/working.md` → **Changelog** and capture pitfalls under **Lessons Learned**.
2. Prefer small commits. When nested inside another repo, this tree keeps **its own** `.git`; publishing pushes **only** this subtree's remote.
3. Language for documentation inside this repo stays **English**.
4. Never commit vault-specific `op://` defaults or raw API keys — operators configure env vars locally.

## Environment

Python **3.10+**. Use `uv pip install -e '.[dev]'` inside `./.venv`. Integration tests spend Tavily credits; gate them with `RUN_TAVILY_INTEGRATION=1`.

## Packaging boundary

Product identity stays **Tavily Skill** (Python package `tavily_skill`, optional CLI console script `tavily-skill`). A `_public`-suffixed **directory name** in a host monorepo marks the publishable export only—it must **not** force the GitHub repository slug to include `public`.
