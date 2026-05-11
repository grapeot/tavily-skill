# AGENTS.md — Tavily Skill

## Layout

- `src/tavily_skill/` — Python package (`cli.py` owns argparse + Tavily calls).
- `tests/` — pytest suite (offline-first).
- `docs/` — PRD, RFC, testing notes, public-release checklist.
- `skills/` — Cursor-agent SKILL entrypoint (English).
- `scripts/run_cli.sh` — convenience runner once `.venv` exists.

## Expectations

1. After substantive edits, append a dated bullet under `docs/working.md` → **Changelog** and capture pitfalls under **Lessons Learned**.
2. Prefer small commits; this repository keeps its own git history independent from `knowledge_working`.
3. Language for documentation inside this repo stays **English**.
4. Never commit vault-specific `op://` defaults or raw API keys — operators configure env vars locally.

## Environment

Python **3.10+**. Use `uv pip install -e '.[dev]'` inside `.venv`. Integration tests spend Tavily credits; gate them with `RUN_TAVILY_INTEGRATION=1`.

## Compatibility shim

The parent workspace keeps `tools/tavily_cli.py` pointing at this tree (`adhoc_jobs/tavily_skill_public/` inside the monorepo). Update both sides when CLI contracts change.
