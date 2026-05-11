# Changelog

## 2026-05-10

- Initial scaffold: Tavily search/extract CLI, public-safe secret handling, English docs and SKILL.
- Monorepo export folder uses `_public` suffix only as a **local reminder** that this subtree is publishable; product stays **Tavily Skill** (`tavily_skill` package); GitHub repo slug stays neutral (no mandatory `public` in remote name). Docs use repo-relative paths only.

## Lessons Learned

- Default artifact directory resolves from current working directory (`tmp/tavily/`); override with `TAVILY_CLI_OUTPUT_DIR` when jobs must isolate outputs.
- **`_*_public` folder suffix**: marks publishable subtree in a host monorepo only—does **not** dictate GitHub repo naming (`tavily-skill` is enough).
