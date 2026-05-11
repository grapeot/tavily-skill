# AGENTS.md — Tavily Skill

## Layout

- `src/tavily_skill/` — Python package (`cli.py` owns argparse + Tavily calls).
- `tests/` — pytest suite (offline-first).
- `docs/` — PRD, RFC, testing notes, working log.
- `skills/` — AI-agent skill entrypoint (`skill_tavily.md`, English).
- `scripts/run_cli.sh` — convenience runner once `.venv` exists.

Treat **repository root** as the default cwd in docs and examples; avoid machine-specific absolute paths.

## Expectations

1. After substantive edits, append a dated bullet under `docs/working.md` → **Changelog** and capture pitfalls under **Lessons Learned**.
2. Prefer small, focused commits.
3. Language for documentation inside this repo stays **English**.
4. Never commit vault-specific `op://` defaults or raw API keys — operators configure env vars locally.

## Environment

Python **3.10+**. Use `uv pip install -e '.[dev]'` inside `./.venv`. Integration tests spend Tavily credits; gate them with `RUN_TAVILY_INTEGRATION=1`.

## Packaging

- Python package: **`tavily_skill`**
- Optional console entry point from `pyproject.toml`: **`tavily-skill`**
