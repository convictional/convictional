---
description: Validate every URL in a scenario's post bodies is live (returns 2xx within a short timeout) before that content is seeded. Use this after authoring or editing post content.
---

# Validate URLs

Post bodies in demo seeds trigger a real HTTP fetch via the `_unfurl_link_preview` hook. Dead URLs slow the seed down and will cause the `test_demo_seed_scenario[<scenario>-seed]` test in CI (15s timeout) to flake or fail.

## Usage

Run from the `app/` directory:

```bash
LOG_LEVEL=info make script ARGS="scripts/seeds/.claude/skills/validate-urls/scripts/validate_urls.py <scenario>"
```

For example:

```bash
LOG_LEVEL=info make script ARGS="scripts/seeds/.claude/skills/validate-urls/scripts/validate_urls.py ellery"
```

## What it checks

For every `.md` file under `scripts/seeds/<scenario>/content/posts/`, extract every `http(s)://` URL from the body and issue a HEAD (falling back to GET on 405) request with:
- Follow redirects on
- 8s timeout per URL
- Parallel up to 8 URLs at a time

Returns exit code 0 if every URL returned 2xx, non-zero otherwise. Prints a table of results with status code and final resolved URL.

## When to run

- Right after authoring or editing post bodies in `content/posts/**/*.md`
- As part of `/implement-seed` verification before reporting success
- Before landing a PR that adds or changes post URLs
