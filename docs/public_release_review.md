# Public Release Review

This note summarizes what was audited before treating `adhoc_jobs/tavily_skill` as publishable outside `knowledge_working`.

## Removed or generalized vs workspace-original CLI

| Original artifact | Risk | Mitigation in this repo |
|-------------------|------|-------------------------|
| Hard-coded `op://dev/dev-api-keys/tavily_api_key` | Vault/item leakage | Secret lookup gated behind operator-provided `ONEPASSWORD_TAVILY_REFERENCE` / `OP_READ_TAVILY_KEY` env vars |
| Error strings documenting internal vault layout | Same | Generic messaging referencing env-driven references |
| Workspace-root `.env` path inferred from script parents | Wrong cwd semantics elsewhere | `.env` discovery walks cwd ancestors only |
| Absolute `/Users/.../.venv` instructions | Personal paths | README documents uv-created `.venv` generically |

## Credential posture for OSS clones

- **Never commit**: `.env`, API keys, 1Password service-account tokens, `tmp/**/*.json` result payloads containing scraped pages from authenticated surfaces.
- **CI recommendation**: inject `TAVILY_API_KEY` via ephemeral secrets manager variables rather than baking references into workflows committed publicly.

## Remaining operator responsibilities

- Set Tavily billing/quota expectations explicitly when exposing CLI wrappers beyond trusted collaborators.
- Scrub downstream transcripts before publishing extracts fetched via authenticated portals even though Tavily returns generic HTTPS URLs.

## Noteworthy negatives / exclusions

- This CLI intentionally avoids crawling authenticated portals — Tavily extract/search policies remain Tavily platform Terms-bound.
