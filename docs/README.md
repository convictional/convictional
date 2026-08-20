# Docs

Reference documentation for the app. Start with the [README](../README.md) if you're setting up for the
first time, or [CONTRIBUTING](../CONTRIBUTING.md) if you're about to open a pull request.

## Getting set up

| Doc | What it covers |
| --- | --- |
| [development](development.md) | Prerequisites, configuration, running several checkouts at once, editor setup |
| [database](database.md) | Tortoise ORM, migrations, local and test databases |
| [testing](testing.md) | The test tiers, running tests, recorded HTTP, browser tests |
| [seeds](seeds.md) | Development seed scenarios and how to write one |
| [integrations](integrations.md) | Configuring Google, Microsoft, Recall.ai, Cloud Tasks, and the rest locally |
| [sandbox](sandbox.md) | A Lima VM for running coding agents off your host |

## How the app works

| Doc | What it covers |
| --- | --- |
| [architecture](architecture.md) | The layers, what belongs in each directory, and the linter that enforces it |
| [company-brain](company-brain.md) | The content corpus, hybrid retrieval, research, goal alignment, and the MCP server |
| [channels](channels.md) | Real-time WebSockets over Postgres `NOTIFY`/`LISTEN` |
| [notifications-spec](notifications-spec.md) | The contract for what notifications the app should produce |
| [notifications-flowchart](notifications-flowchart.md) | The as-built trace of how an event becomes a notification |
| [react-migration](react-migration.md) | Migrating the frontend from htmx/Alpine to React islands |
| [mobile](mobile.md) | When to reach for media queries versus the `@mobile:` container query |
| [linter_wishlist](linter_wishlist.md) | Conventions we'd enforce with a linter if we could |

## Running it yourself

| Doc | What it covers |
| --- | --- |
| [self-hosting](self-hosting.md) | Docker, the settings a deployment needs, the reference GCP setup |
