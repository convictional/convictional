# Architecture

This is a guide to illustrate the architecture basics of the app.

---

## Overview

The main thing to keep in mind is **you can't mess this up too bad because we have a linter** which enforces the imports, which is effectively the architecture. So don't stress, if you have questions please reach out.

`.importlinter` is the authority. It declares five layers, each of which may import only from those below
it:

```
integrations  →  app  →  infra  →  config  →  lib
```

- **`/integrations`** — third-party service integrations: data connections, OAuth, webhooks. The top layer,
  so it may import from `app`.
- **`/app`** — the core application, backend and frontend. Only code that would be meaningful in this app.
- **`/infra`** — utilities for talking to infrastructure: the database, email, background jobs, storage,
  caching, LLMs, vectors.
- **`/config`** — configuration for all of the above: settings, logging, deploy definitions, infrastructure
  as code.
- **`/lib`** — pure, domain-agnostic utilities with zero application dependencies. Only the standard library
  and third-party packages.

Alongside those: `/migrations` holds the [Aerich](https://github.com/tortoise/aerich) migrations,
`/scripts` holds scripts run through `make script`, `/static` holds served assets, and `/tests` mirrors the
application structure (see [testing](testing.md)).

Don't add a new top-level layer — the layering is a deliberate constraint, not a starting point.

### `/app/helpers` versus `/lib`

Both hold utilities, and the line between them is about audience rather than purity. `app/helpers` is
presentation: formatting and displaying data in templates. `lib` is standalone utilities that could be
extracted into a package — HTML sanitization, token encoding, pure data transformations. If it's about
presenting data to users it's a helper; otherwise it's `lib`.

## The stack

- **API** — [FastAPI](https://fastapi.tiangolo.com), serving both HTML and a JSON API.
- **Database** — Postgres 18 via the [Tortoise ORM](https://tortoise.github.io). It also carries the cache,
  the job queue, and full-text search.
- **Vectors** — [pgvector](https://github.com/pgvector/pgvector), with embeddings from
  [OpenAI](https://platform.openai.com/docs/guides/embeddings).
- **Inference** — the [Anthropic API](https://docs.anthropic.com), via
  [instructor](https://github.com/567-labs/instructor) for structured output.
- **Background jobs** — in-process by default; [Google Cloud Tasks](https://cloud.google.com/tasks) hitting
  FastAPI endpoints in the reference deployment.
- **Storage** — local disk by default, [Google Cloud Storage](https://cloud.google.com/storage) when
  configured.
- **Real-time** — WebSockets over Postgres `NOTIFY`/`LISTEN`. See [channels](channels.md).

### Frontend

The frontend is migrating from [htmx](https://htmx.org)/[Alpine.js](https://alpinejs.dev) to
[React](https://react.dev). Islands were the stepping stone rather than the destination: much of the app is
now a client-routed SPA, and the islands that remain are React components mounted into the Jinja pages that
haven't been cut over. See [react-migration](react-migration.md) for the strategy and the Client-Side Router
ADR.

Two rendering modes coexist, with a full-document boundary between them:

- **The SPA.** `app/routers/spa.py` serves a near-empty shell (`layouts/spa.html.jinja`) for every path in
  `SPA_ROUTES` and [TanStack Router](https://tanstack.com/router) takes over from there — the mailbox,
  documents, posts, goals, chats, email threads, notifications, and organization settings. Its entry point,
  `app/javascript/spa.tsx`, boots the router and nothing else: no Alpine, no htmx, no island mounts.
- **Server-rendered pages.** Everything else is Jinja with htmx and Alpine, booted by
  `app/javascript/main.ts`, with React islands mounted into the page by `mountIsland`. Meetings, search,
  profiles, groups, and the settings and admin pages are still here.

Navigating between client routes is a `<Link>`; navigating to a page that hasn't been cut over is a full
document load. `<Link>` only knows registered routes, so aiming one at an unmigrated path is a type error
rather than a silent fallback.

- **Route tree** — lives in `react/app/`, a top layer sealed above `features → composites → shared → ui`. It
  may import from below and nothing below may import it, enforced by the `app-is-the-top` rule in
  `.dependency-cruiser.cjs`. Features get typed routes through a global `Register` augmentation rather than
  by importing the tree.
- **State** — server state lives in [TanStack Query](https://tanstack.com/query), in one module-level client
  shared by the SPA and every island so the cache doesn't fragment. Queries backed by a real-time channel
  spread in `channelQueryDefaults` (`react/shared/queryClient.ts`): the channel is their freshness source, so
  they never background-refetch and a channel handler patches or invalidates the cache instead. Reads with no
  channel behind them keep TanStack's normal defaults. [Zustand](https://zustand-demo.pmnd.rs) holds UI and
  ephemeral state only.
- **JS** — bundled by [Vite](https://vite.dev) and served as a static asset. Rich text is
  [ProseMirror](https://prosemirror.net) with [Yjs](https://yjs.dev) for collaborative editing.
- **CSS** — [Tailwind](https://tailwindcss.com) with [daisyUI](https://daisyui.com), compiled and minified
  by the Tailwind CLI. The compiled output only includes classes actually used in templates and components.

Use `make server` for development — it compiles CSS and JS and watches for changes.

## Inside `/app`

Here are short descriptors for each type of code with `/app`, use them to guide your thinking on where to put code.

**`/app/mailers`**

These are mailer classes that compose system email messages using `/app/models` and render templates from `/app/templates/mailers`. Each mailer is a dataclass that inherits from the base `Mailer` class and uses instance methods to send emails.

**`/app/helpers`**

These contain general reusable presentation logic for rendering `/app/templates`, like Markdown, date formatting, etc.

**`/app/jobs`**

These coordinate `/app/models` and others to perform long-running background tasks. Think of them like services of background jobs.

**`/app/middleware`**

These help with HTTP details that globally affect what requests `/app/routers` send and receive. For example, maintaining the right protocol from the proxy headers.

**`/app/models`**

This contains code that represents data and models the real-world domain. The rest of the app uses them to achieve the desired functionality. They may not depend on each other to decouple and simplify modeling and business logic.

Models have their own layering, also linted: `workspaces` → `collaboration` → `accounts`. A workspace model may import from collaboration; the reverse is a lint failure.

Comments are modeled per-resource, not generically: each commentable resource owns its own `*Comment` model in the workspaces layer, scoped to that resource's id — `DocumentComment.document_id`, `GoalComment.goal_id`, `PostComment.post_id`, `EmailThreadComment.email_thread_id`, `ChatMessage.chat_id`. A comment always belongs to a resource; there is no generic workspace-level comment model.

**`/app/presenters`**

They assemble models for presentation. Only use when needed, but these are critical for combining `/app/models` that seem like they need to depend on each other.

**`/app/prompts`**

Content for prompts to send to the LLM, used by `/app/jobs` to build the LLM calls.

**`/app/routers`**

These coordinate `/app/models`, `/app/jobs`, and others to respond to HTTP requests. They also use `/app/presenters` and `/app/templates` to render HTML.

**`/app/routers/api`**

JSON API endpoints for React islands. Shared code is split by concern: `schemas.py` (Pydantic models), `serializers.py` (model-to-response transforms), `streams.py` (channel/broadcast helpers), and `dependencies.py` (FastAPI dependencies only). These follow a layered structure enforced by import linting. API routers can import from existing HTML router helpers, but not vice versa.

**`/app/templates`**

These are templates and partials used to render HTML for users.
