# Convictional

Convictional keeps teams aligned on their goals. It's a workspace where the things a company decides live
next to the work itself: goals and the updates against them, meetings with transcripts, chats, documents,
posts, email threads, and a record of decisions — all searchable, and readable by AI that can answer
questions across the whole of it.

## Features

- **Goals** — nested goals with owners, status, updates over time, and alignment between them.
- **Meetings** — a bot joins your calls, transcribes them, and the transcript becomes searchable content.
- **Chats** — real-time messaging, direct and group.
- **Documents** — collaborative rich-text editing, backed by CRDTs.
- **Posts** — long-form internal writing with threaded comments.
- **Email** — a shared mailbox over Gmail, so external threads sit beside internal work.
- **Decisions** — a durable record of what was decided and why. Logged by people, never by an agent.
- **Search** — full-text and semantic search across everything above.
- **Research** — ask a question and get an answer drawn from your workspace, on demand or on a schedule.
- **MCP server** — expose your workspace to agents over [MCP](https://modelcontextprotocol.io).

## The company brain

Everything a team writes lands in one corpus and stays retrievable. Meetings, posts, documents, chats, email
threads, decisions, and goals all normalize into a single `Content` table, and every row carries both a
full-text index and an embedding. That table is what the AI features read.

- **Hybrid retrieval in one query.** Dense retrieval over pgvector embeddings and sparse retrieval over
  Postgres full-text are fused in a single statement — weighted 70/30 toward dense, then balanced across
  content categories so a question about a project doesn't come back as ten meetings and nothing else. No
  search cluster, no separate vector database, no sync job between them.
- **Permissions live inside that query.** Access is a `WHERE` clause, not a filter applied to the results:
  retrieval only ever sees content shared to the organization or shared explicitly with the person asking.
  A private document is invisible to everyone else's search, everyone else's research, and every agent.
- **Research is a loop, not a lookup.** Ask a question and the app plans a set of queries, runs them,
  reviews what came back, and decides whether to go deeper. Answers come back with citations to the source
  content. Run one on demand, or on a schedule that arrives by email.
- **Goals are scored against the work.** Posts and meetings are matched to the organization's goals — a
  vector pass narrows the field, then a model judges each candidate using few-shot examples drawn from
  earlier alignment decisions.
- **Agents get the same brain.** The MCP server exposes search, content, and the goal tree over
  [MCP](https://modelcontextprotocol.io), authenticated per user and bound by the same permission rules — so
  an agent reaches the workspace through the front door instead of a scraping integration.

How it's built, and where to change it, is in [company-brain](docs/company-brain.md).

## Stack

[FastAPI](https://fastapi.tiangolo.com) and Python 3.13, [Tortoise ORM](https://tortoise.github.io) over
Postgres 18 with [pgvector](https://github.com/pgvector/pgvector). The frontend is
[React 19](https://react.dev) with [TanStack](https://tanstack.com) Router and Query, plus
[Tailwind 4](https://tailwindcss.com) and [daisyUI](https://daisyui.com), bundled by
[Vite](https://vite.dev). Much of the app is a client-routed SPA; a legacy
[htmx](https://htmx.org)/[Alpine.js](https://alpinejs.dev) layer still serves the pages that haven't been cut
over — see [react-migration](docs/react-migration.md).

**Postgres is the only service you need.** No Redis, no message broker, no search cluster: the cache, job
queue, full-text search, and vector search all live in the database.

## Quick start

You'll need [uv](https://docs.astral.sh/uv/), Postgres 18 with pgvector, and Node at the version in
`.nvmrc`. See [development](docs/development.md) for the details and platform notes.

```bash
make install                    # Python and JS dependencies, plus libmagic
```

Create `.env.secrets` with keys for the two model providers:

```
ANTHROPIC_API_KEY={value}
OPENAI_API_KEY={value}
```

Then set up the database and start the app:

```bash
make db_create                  # create this checkout's database
make db_seed ARGS="ellery"      # populate it with a fictional 11-person company
make server                     # start the app
make browser_open               # open it
```

The startup banner prints your URL. The port is derived from the checkout directory, so several clones can
run at once without colliding.

Development runs with fake auth, so the sign-in screen lists the seeded users — click one to sign in. No
OAuth setup needed until you're working on authentication itself.

## Common commands

The `Makefile` is the interface to everything; `make help` lists all of it.

| Command | Purpose |
| --- | --- |
| `make server` | Run the app with hot reload |
| `make validate` | Lint and type-check — must pass before shipping |
| `make test_parallel` | Run the Python test suite in parallel |
| `make test ARGS="path/to/test.py"` | Run one test file or directory |
| `make test_javascript` | Run the Vitest suite |
| `make db_migrate ARGS="--name my_change"` | Generate a migration from model changes |
| `make db_upgrade` | Apply pending migrations |
| `make db_reset` | Drop and recreate the database |
| `make console` | An IPython REPL with the app loaded |

## Self-hosting

The app ships as a Docker image and needs a Postgres 18 database with pgvector, an
`ANTHROPIC_API_KEY`, and an identity provider so people can sign in. Everything else is optional and gated
on its own credentials.

```bash
docker build -t convictional .
```

See [self-hosting](docs/self-hosting.md) for the settings that matter, and
[integrations](docs/integrations.md) for turning individual integrations on.

## Documentation

| Doc | What it covers |
| --- | --- |
| [development](docs/development.md) | Local setup, running several checkouts, editor config |
| [architecture](docs/architecture.md) | How the code is laid out and the layering the linter enforces |
| [company-brain](docs/company-brain.md) | The content corpus, retrieval, research, goal alignment, and MCP |
| [database](docs/database.md) | The ORM, migrations, and schema workflow |
| [testing](docs/testing.md) | Running tests, recorded HTTP, the test tiers |
| [self-hosting](docs/self-hosting.md) | Docker, configuration, deployment |
| [integrations](docs/integrations.md) | Google, Microsoft, Recall.ai, Slack, and friends |
| [seeds](docs/seeds.md) | The development seed scenarios |
| [channels](docs/channels.md) | Real-time WebSockets over Postgres `NOTIFY`/`LISTEN` |
| [react-migration](docs/react-migration.md) | Moving the frontend from htmx/Alpine to React islands |
| [notifications-spec](docs/notifications-spec.md) | What notifications the app should produce |
| [sandbox](docs/sandbox.md) | A Lima VM for running coding agents off your host |

The full index is in [docs](docs/README.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Contributors are expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Please report vulnerabilities privately — see [SECURITY.md](SECURITY.md). Don't open a public issue for
them.

## License

See [LICENSE](LICENSE).
