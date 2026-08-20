# Convictional Project Guide

## Makefile

See @Makefile for running tests, linting, running scripts, dependencies, or other common tasks. You should always use the commands from the Makefile because you might not know the various setup needed.

### Validating your changes

After making changes, you MUST run `make validate` and fix every error it reports before declaring work complete. This runs lint and type checks (Python and TypeScript) in parallel. **It does not matter if a failure existed before your changes** — if `make validate` fails, you MUST fix it. Do not skip, suppress, or work around failures.

`make validate` does **not** run tests. You are responsible for running the tests relevant to your changes:

- Tests mirror the application structure. Changes to `app/models/chat.py` map to `tests/unit/models/test_chat.py` and/or `tests/integration/models/test_chat.py`. Changes to `app/routers/foo.py` typically map to `tests/integration/routers/test_foo.py`.
- Run a specific file or directory: `make test ARGS="tests/integration/models/test_chat.py"` or `make test ARGS="tests/integration/models/"`.
- For changes to widely-used code (helpers, shared models, base components, middleware), run the broader directory it lives under, since many tests can depend on it indirectly.
- If you touched JS/TS, run `make test_javascript`.
- Use `make test_parallel` (full Python suite) only when the change is broad enough that targeted runs aren't sufficient — e.g., touching shared infrastructure, a base model, or app startup. CI runs the full suite on every PR; you don't need to reproduce that locally for typical changes.

When you report work as complete, state explicitly which tests you ran. If you didn't run tests because the change was non-functional (docs, comments), say so.

### Quick Reference

| Command                                   | Purpose                                               |
| ----------------------------------------- | ----------------------------------------------------- |
| `make validate`                           | Run lint and types in parallel — must pass to ship    |
| `make test ARGS="path/to/test.py"`        | Run a specific test file or directory                 |
| `make test_parallel`                      | Run the full Python suite in parallel (use sparingly) |
| `make test_javascript`                    | Run the JS/TS test suite                              |
| `make test_unit`                          | Run all unit tests                                    |
| `make test_integration`                   | Run all integration tests                             |
| `make test_browser`                       | Run all headless browser tests                        |
| `make db_migrate ARGS="--name foo"`       | Generate auto migration                               |
| `make db_migrate_empty ARGS="--name foo"` | Create manual migration                               |
| `make db_upgrade`                         | Apply pending migrations                              |
| `make db_create_parallel_tests`           | One-time setup for parallel tests                     |
| `make console`                            | REPL with app context                                 |
| `make script ARGS="scripts/foo.py"`       | Run script with PYTHONPATH                            |
| `make job ARGS='job_type {}'`             | Run background job directly                           |
| `make browser_open`                       | Open the app in the browser                           |
| `make server`                             | Start the development server                          |

## Browser & Chrome DevTools MCP

Each checkout runs on a unique port derived from its directory name. Use `make browser_open` to get the correct URL and open the app in the browser. When using Chrome DevTools MCP tools, run `make browser_open` first to determine the app URL for the current directory, then use that URL with `navigate_page` and other MCP tools.

## Architecture & Constraints

### Layers

From top to bottom:

- Integrations (/integrations): Third-party service integration like data connections, OAuth authentications, etc.
- Application (/app): Core application backend and frontend code.
- Infrastructure (/infra): Utilities for working with dependent infrastructure like the database, email, background jobs, storage, etc.
- Configuration layer (/config): Configuration for the above, like logging and settings.
- Library (/lib): Pure, domain-agnostic utilities with zero application dependencies.

### Dependencies

- Lower layers cannot import from higher layers (e.g., /infra cannot import from /app)
- The /lib layer sits at the bottom and can only depend on standard library and third-party packages
- Models follow layering: workspaces → collaboration → accounts (a workspace model can import from collaboration, but not vice versa)
- Don't create new layers like `/services` directory because you don't have architectural authority.


### Distinguishing /app/helpers from /lib

- **app/helpers/**: Presentation layer utilities for formatting and displaying data in templates (date formatting, string formatting for display, template helpers)
- **lib/**: Pure, reusable utilities with no app-specific dependencies (HTML sanitization, token encoding, pure data transformations)
- **Rule of thumb**: If it's about presenting data to users, it goes in app/helpers. If it's a standalone utility that could be extracted into a library, it goes in lib/.

### Whitespace: display renderers preserve, derived extractors collapse

Authored whitespace (space runs, single line breaks, blank-line runs) is significant and rendered byte-exactly — but only on **display** surfaces. Two categories, do not cross them:

- **Display renderers preserve whitespace.** react-markdown in-app (`app/javascript/react/composites/markdown/Markdown.tsx`) and `render_email_html` (email) render authored content to a user-visible surface and are held to the whitespace-fidelity contract (`tests/fixtures/markdown_whitespace/`). Don't regress one to collapse whitespace.
- **Derived / plain-text extractors keep collapsing whitespace.** `markdown_to_plain_text` (`lib/markdown.py`), `html_to_plain_text` (`app/helpers/strings.py`), `og_description` (`app/helpers/strings.py`), and the `text/plain` MIME part (`integrations/google/email_mime_builder.py`) produce derived text that feeds **no** display surface — collapsing is correct. Don't "fix" one to preserve whitespace.

## Code Style

Before creating a new file, make sure you look at other files in the same directory. This will give you a sense of our style, which you tend to not follow without examples.

### Importing

- You tend to put imports inline. Use absolute imports to avoid ambiguity, provide easier refactoring, and align to PEP8.
- Always include imports at the top of the file to avoid runtime performance hits, and keep things readable and aligned to PEP8.

### Logging

- You log too much. Don't log high volume or low value events, and don't log redundantly because this makes it harder to debug.
- This application uses Sentry to monitor exceptions so you don't have to log every exception/error.
- If you are in a spot where you need to log an exception (i.e. the exception is otherwise swallowed), prefer the more modern logger.exception() which automatically includes trace info and will be sent to Sentry.
- Use logger.error() only for general error messages without an exception or when you don't need the traceback.

### Datetimes

- Avoid using dateutil.tz and pytz, because this is modern Python and these libraries are buggy and confusing.
- Use zoneinfo.ZoneInfo and datetime.UTC because they work cleanly and intuitively.

### Typing

- This is the modern Python at 3.13, so use modern typing improvements.
- Use the modern | instead of Union because of brevity.
- Use the built in types (e.g. list instead of typing.List and dict instead of typing.Dict) to limit importing.

### Commenting

- Names are the first line of documentation. If a class, function, or variable name communicates its purpose clearly, a comment restating it is noise.
- Don't add comments that describe _what_ the code does — the code already says that. Do add comments that explain _why_ a decision was made, especially when the reason isn't obvious from the surrounding code.
- Good candidates for comments: framework boundary interactions (e.g. why HTMX and React coordinate a certain way), non-obvious constraints or invariants, workarounds with context on what they're working around, and design choices where an alternative approach might seem more natural.
- We tend not to use docblocks because of how noisy they are and often trivial or self-explanatory. You may add them to explain particularly complex or non-obvious behavior or side-effects.
- Comment the durable _why_, never a transient fact. A fact nothing enforces becomes a lie when it drifts: consumer/caller counts, "currently/for now/soon", incident history ("the bug that tripped the rate limiter"), or parity with code being deleted ("mirrors the Alpine directive"). Test: "will this still be true in 6 months?" If not, state the invariant instead. (Exception: naming a live mechanism the code depends on _today_ — e.g. an `htmx:load` listener — is durable, not transient.)

## Visit tracking (read state / "last seen" / viewed / unread / "what's new")

Per-user, per-workspace read state lives in one place: the `Visit` model (`app/models/collaboration/workspace.py`, `# Visits` section). **Before building any "unread", "mark as seen", "last viewed", "who has seen this", or "what's new" behavior on a workspace resource, reuse Visit — do not add a parallel read-state store.**

- **Record a visit (write):** backend `await Visit.record(user_id, workspace_id, last_event_id=None)`; React `useWorkspaceVisitRecording(workspaceId)` (`app/javascript/react/shared/hooks/useVisitRecording.ts`). All roads lead to the shared endpoint `POST /api/workspaces/{id}/visits`.
- **Read visit state:** `ViewStateResolver(workspace=…).view_states_for(user_ids)` for per-collaborator "seen-by"; `visit.updated_at` (current view) vs `visit.last_visit_at` (prior view) for "new since last visit" (see `presenters/posts.py` → `WhatsNew`).
- **Adding a new collaboratable resource?** Record a visit on its show/load surface exactly like the existing resources (documents, posts, and email threads all mount `useWorkspaceVisitRecording`). There is no per-resource variation — the uniformity is a convention, not enforced, so match it.
- **Not the same as** the mailbox `read/unread` mechanism (`MailboxEntry`-based) or `User.last_seen_at` (global presence). Chats deliberately layer a Visit read-cursor on top of the mailbox unread state.

## Frontend

The app is migrating from HTMX/Alpine.js to React using an islands architecture. See `docs/react-migration.md` for the full strategy. Both stacks coexist during the transition.

New interactive components are built as React islands — see `app/javascript/react/CLAUDE.md`. The existing HTMX/Alpine templates have their own rules in `app/templates/CLAUDE.md`.

## Backend (FastAPI + Tortoise ORM)

This app uses FastAPI with Tortoise ORM for the backend.

### Critical Rules

1. **Always use Makefile commands** - Never run `uv run pytest`, `python scripts/...`, or `aerich` directly. Use `make test`, `make script`, `make db_migrate`, etc.

2. **Use transactions for multi-step operations** - Wrap related database operations in `async with transaction() as connection:` and pass `using_db=connection` to all queries.

### Common Mistakes

- Running commands without Makefile (`uv run pytest` instead of `make test`)
- Forgetting `using_db=connection` inside transaction blocks
- Using inline imports instead of imports at the top of files
- Using `pytz` or `dateutil.tz` instead of `zoneinfo.ZoneInfo` and `datetime.UTC`
