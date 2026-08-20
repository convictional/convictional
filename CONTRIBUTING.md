# Contributing

Thanks for your interest in contributing. This covers how to propose a change and what's expected of it.
For getting the app running, see the [README](README.md) and [development](docs/development.md) — this
document assumes you already have.

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting bugs

Open an issue with enough for someone else to reproduce it: what you did, what happened, what you expected,
and the version or commit you saw it on. A failing test is the most useful bug report there is.

If the bug has security implications, don't open an issue — follow [SECURITY.md](SECURITY.md) instead.

## Proposing features

Open an issue describing the problem before writing the code. Start with what's hard today and who it's hard
for; a proposal framed as a problem can be solved more than one way, and the discussion is where that gets
decided. Large changes that arrive as a finished pull request are hard to accept, however good the code —
there's nowhere left to weigh in.

## Making a change

Work on a branch and open a pull request against `main`.

Keep the diff traceable to the thing you're fixing. Don't reformat surrounding code, rename adjacent
symbols, or refactor what isn't broken — those changes are welcome, just not smuggled in. If your change
leaves an import or a helper unused, remove it; if you spot unrelated dead code, mention it rather than
deleting it.

Before you open the pull request:

- **`make validate` must pass.** It runs lint and type checks for both Python and TypeScript, in parallel.
  It doesn't matter whether a failure predates your change — if validate fails, fix it. Don't suppress it.
- **Run the tests that cover what you touched.** `tests/` mirrors the application structure, so a change to
  `app/models/chat.py` maps to `tests/unit/models/test_chat.py` and `tests/integration/models/test_chat.py`.
  For shared code — helpers, base models, middleware — run the whole directory it lives under. See
  [testing](docs/testing.md).
- **Commit migrations alongside the model changes that produced them.** CI regenerates migrations and fails
  on any diff, so a model change without its migration won't merge. See [database](docs/database.md).
- **Write a description that explains why.** The diff already says what changed.

New browser tests are the one thing to raise before writing: they're slow and fragile, so the suite is kept
deliberately small. Open the discussion first.

## What CI runs

Every pull request runs:

| Check | What it does |
| --- | --- |
| Linting | `make lint` — ruff, import-linter, djlint, ESLint, dependency-cruiser, and Spectral on the generated OpenAPI spec |
| Types | `make types` — mypy and `tsc` |
| Tests | The Python suite in parallel against Postgres. Also fails the build on `RuntimeWarning: coroutine … was never awaited` |
| JavaScript tests | `make test_javascript` |
| Seeds | Seeds a fresh database, so seed code can't rot |
| Migrations | Regenerates migrations and fails if that produces a diff |
| Security | [gitleaks](https://github.com/gitleaks/gitleaks) secret scanning and zizmor workflow auditing |

Browser tests run nightly rather than per-pull-request.

### Secret scanning

gitleaks scans the full diff of **every commit on the branch**, not just the working tree. If it flags
something genuinely safe — a test fixture, an example token, a docs snippet:

- **One line:** append `# gitleaks:allow` (or `// gitleaks:allow`).
- **A file or pattern:** add a `paths` or `regexes` entry to the `[allowlist]` block in `.gitleaks.toml`.

Because it walks every commit, an inline allow on the current line doesn't help when the value was
introduced by an earlier commit on the branch and changed later — the original commit still trips the scan.
Two ways out: rewrite the branch with `git rebase -i` to drop or amend that commit, or add its SHA to
`[allowlist].commits`. Rewriting is right when the value really is sensitive; allowlisting is right when
it's a true false positive and rewriting would be disruptive.

**If the value is a real secret, rotate it first.** Rewriting history doesn't remove it from anyone who
already fetched the branch.

## Conventions

The import linter is the real authority on structure — `.importlinter` defines the layers
(`integrations → app → infra → config → lib`, each importing only downward) and the per-package rules.
[architecture](docs/architecture.md) explains what belongs where; `CLAUDE.md` and the nested `CLAUDE.md`
files carry the house style in more detail.

The things most often gotten wrong:

- **Imports at the top of the file, and absolute.** Not inline, not relative.
- **`zoneinfo.ZoneInfo` and `datetime.UTC`** — never `pytz` or `dateutil.tz`. Ruff enforces this.
- **Modern typing** — `X | None`, built-in `list`/`dict`. Python is 3.13 here.
- **Comment the durable *why*, not the *what*.** Names are the first line of documentation. A comment
  restating the code is noise; a comment explaining a non-obvious constraint or a workaround is valuable.
  Avoid facts that nothing enforces — caller counts, "for now", parity with code being deleted — because
  they become lies when they drift.
- **Whitespace fidelity.** Display renderers preserve authored whitespace byte-exactly; derived plain-text
  extractors collapse it. Don't cross those two.
- **Externally-hosted JavaScript needs a
  [Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity)
  hash.** Generate the `<script>` tag with the [SRI Hash Generator](https://www.srihash.org).

`make format` fixes what's mechanically fixable. `docs/linter_wishlist.md` lists conventions we'd enforce
with a linter if we could — worth a skim, since nothing will catch them for you.

## Security issues

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md). Please don't open a public
issue or pull request for a security report.
