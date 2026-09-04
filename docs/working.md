# Changelog

## 2026-05-10

- Initial scaffold: Tavily search/extract CLI, credential-safe defaults (env / optional `op` reference), English docs and SKILL.
- Documentation uses paths relative to repository root only.

## 2026-05-28

- Renamed the workspace checkout to `adhoc_jobs/tavily_skill/` and retired the old workspace-level shim; canonical invocation is `.venv/bin/python -m tavily_skill` or `scripts/run_cli.sh` from the standalone repo.

## 2026-07-29

- Removed the search answer option and answer fields from requests, normalized payloads, status summaries, and schemas.

## 2026-09-04

- Documented `TAVILY_CLI_OUTPUT_DIR` in the skill file (new "First-time setup" section: recommend a dedicated persistent output directory once during initial setup), README, and `.env.example`.

## Lessons Learned

- Default artifact directory resolves from current working directory (`./tmp/tavily/`); override with `TAVILY_CLI_OUTPUT_DIR` when jobs must isolate outputs.
- Prefer `.venv/bin/python -m tavily_skill` or `scripts/run_cli.sh` over relying on a shell activation side effect; direct interpreter paths survive workspace-level routing changes better.
- Enforce untrusted upstream-field exclusions in response normalization rather than relying on agent instructions.
