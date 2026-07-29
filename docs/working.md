# Changelog

## 2026-05-10

- Initial scaffold: Tavily search/extract CLI, credential-safe defaults (env / optional `op` reference), English docs and SKILL.
- Documentation uses paths relative to repository root only.

## 2026-07-29

- Removed the search answer option and answer fields from requests, normalized payloads, status summaries, and schemas.

## Lessons Learned

- Default artifact directory resolves from current working directory (`./tmp/tavily/`); override with `TAVILY_CLI_OUTPUT_DIR` when jobs must isolate outputs.
- Enforce untrusted upstream-field exclusions in response normalization rather than relying on agent instructions.
