# Changelog

## 2026-05-10

- Initial scaffold: extracted Tavily CLI from workspace `tools/tavily_cli.py`, public-safe secret handling, English docs and SKILL.

## Lessons Learned

- Default artifact directory resolves from current working directory (`tmp/tavily/`); override with `TAVILY_CLI_OUTPUT_DIR` when jobs must isolate outputs.
