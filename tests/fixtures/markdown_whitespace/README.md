# Markdown whitespace fidelity cases

Shared cases for the **WYSIWYG whitespace-fidelity** initiative (byte-exact
RTE→render parity across the in-app and email surfaces). See the plan:
`support/docs/plans/2026-07-01-wysiwyg-whitespace-fidelity-unification.md`.

These cases are the single contract both renderers are held to:

- **Client / in-app** — `react-markdown` pipeline (`app/javascript/react/composites/markdown/Markdown.tsx`).
  Consumed by vitest tests under `tests/javascript/` (import `cases.json` by relative path).
- **Server / email** — `render_email_html` (`app/helpers/html.py`) + `sanitize_email_html_content`
  (`lib/html.py`), and the in-app/OG `render_markdown` (`app/helpers/markdown.py`).
  Consumed by pytest tests under `tests/`.

## Status: contract complete (2026-07-01)

The cases and their **empirically observed** current HTML were captured by the contract spikes
(2026-07-01) by running the real client and server renderers. The whitespace contract (this
document) is now settled and `target_html` — the whitespace-tight canonical form both renderers
must reduce to — is **filled** for every case that is part of the enforced contract. Cases
excluded from the contract carry `target_html: null` with an explanatory `status` (`descoped` for
trailing spaces, `rejected` for the inline-`<br/>` candidate a spike ruled out).

**Enforced as of PR4 (2026-07-08).** The cases are now wired into CI:
- **Per-surface raw pins** — `in_app_target` by `tests/javascript/react/composites/markdown/whitespaceConformance.test.tsx`
  (PR2), `email_target` by `tests/unit/helpers/test_html.py::test_email_target_conformance` (PR3).
- **Cross-surface parity** — `tests/unit/helpers/test_whitespace_parity.py` (PR4) reduces each surface through the
  single central normalizer (`tests/helpers/whitespace_parity.py`) and asserts
  `normalize(render_email_html(wire)) == normalize(in_app_target) == target_html`. This unit test rides
  `make test_parallel` on every PR (the merge gate). `code_block_indented` is excluded from the cross-surface set (see
  below); browser visual + E2E RTE→render checks live in `tests/browser/test_whitespace_fidelity.py` (nightly /
  `browser-tests` label).

## Case schema (`cases.json`)

```jsonc
{
  "name": "interior_run_paragraph",       // stable id
  "category": "interior_run",              // see categories below
  "description": "human-readable",
  "wire": "a   b\n",        // the serialized editor output / storage form (Markdown)
  "observed": {
    "in_app_html": "<p>a   b</p>",   // current react-markdown output (pre-conformance)
    "email_post_nh3_html": "<div><div>a   b</div></div>" // current server output post-nh3
  },
  "target_html": null,                     // whitespace-tight canonical HTML, or null if not enforced
  "status": "green",                       // see status legend
  "notes": "..."
}
```

### Categories
`interior_run`, `leading`, `trailing`, `hard_break`, `blank_run`, `structural`, `control`, `escalation`.

### Status legend
(Matches `cases.json` `_meta.status_legend` — keep the two in sync.)
- `green` — Markdown carries it losslessly through both renderers; remaining work is CSS
  (`white-space: pre-wrap`) and/or the cosmetic-`\n` strip and (for empty blocks) emitting the
  canonical wrapped form. No serializer/wire change.
- `pr1-gated` — requires a PR1 serializer change (fix a data-loss bug, or emit the settled
  encoding). `wire` shows the intended post-PR1 form.
- `descoped` — trailing-space fidelity, excluded from the enforced contract per decision 3 (the
  single accepted concession). `target_html` is null; not asserted.
- `escalation` — **not expressible in Markdown at all** (in-cell hard break). Accepted-as-flattened
  per the contract decision; `target_html` is the flattened form both surfaces already agree on.
- `rejected` — a candidate encoding a contract spike rejected; kept for the record, not a target.
  `target_html` is null.
- `control` — must-not-regress (code blocks). The email path currently **regresses** code blocks
  (nh3) until the separate `<pre>`/`<code>`-aware sanitizer fix lands.

## Key spike finding for the parity assertion (PR4)

Literal **byte-identical** HTML across the two surfaces is **not** achievable, for reasons
independent of fidelity:
- empty block renders as `<p><br/></p>` (in-app) vs `<div><br></div>` (email);
- the client **decodes** entities (`&#x20;` → space, `&nbsp;`/`&#160;` → space) while the server
  **preserves** them as literal entity text, and nh3 serializes raw NBSP (U+00A0) to `&nbsp;`;
- the client lifts a standalone `<br/>` to the root; the server wraps it in a block.

So the PR4 parity check must compare **normalized** HTML (canonical empty-block tag, decoded
entities, normalized NBSP) or assert DOM/visual equivalence — not raw string equality. This
corrects the plan's original "byte-identical" framing.

### Cross-surface exclusion: `code_block_indented`

One case is a per-surface must-not-regress fixture but **not** a cross-surface parity target, so PR4's parity test
carries it in a documented `CROSS_SURFACE_EXCLUDED` set. react-markdown keeps a trailing `\n` inside `<code>`
(`line two\n`) while the email renderer drops it (`line two`); `<pre>`/`<code>` is verbatim/exempt from
normalization, so the normalizer cannot (and must not) bridge it — `code_block_fenced` proves the trailing `\n`
must be *preserved* in code. Indented code is also legacy/paste-only (the editor emits fenced blocks), so it is not
authored-fidelity output. It stays pinned per-surface by PR2/PR3; `code_block_fenced` is the cross-surface
code-block guard.
