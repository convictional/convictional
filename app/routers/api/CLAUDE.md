# JSON API design

The JSON API under `app/routers/api/` is the contract for React islands and any future external client. Conventions are being tightened over time — this file is the running record. Apply them to new endpoints, and follow them when modifying existing ones.

**North star:** [Stripe](https://docs.stripe.com/api) and [GitHub](https://docs.github.com/en/rest) for shape and rigor. We want endpoints an external developer could read without surprise — predictable status codes, list envelopes, explicit state, no implicit toggles, no smuggled side effects.

**Enforcement:** `make lint_api_spec` runs [Spectral](https://docs.stoplight.io/docs/spectral) against the generated OpenAPI schema (see `.spectral.yaml`). It catches the mechanical mistakes (bare-array responses, missing 204 on DELETE). The rules below are the broader contract that humans enforce in review.

**Imports:** `app/routers/api/` can import from existing routers. Existing routers cannot import from `api/`.

## Status codes

Match the response code to what actually happened. Codegen clients and external consumers branch on these.

Success:

- `200 OK` — successful GET, PATCH, or a POST that updates an existing resource (e.g. idempotent resubmit of an access request).
- `201 Created` — POST that brings a new resource into existence (`POST /api/email_threads`, collaborator add, etc.). When the same endpoint can either create or refresh, override the default per-request with `response.status_code = status.HTTP_200_OK` on the refresh branch, mirroring `app/routers/api/push.py`.
- `202 Accepted` — POST that enqueues async work and returns before the work finishes (`scheduled_research/run_now`, `scheduled_research/preview`).
- `204 No Content` — DELETE (always) or PATCH where the client doesn't need the response body.

Client errors:

- `400 Bad Request` — malformed request (unparseable JSON, missing required path/query params). FastAPI raises this on syntax-level issues; do not use it for semantic validation failures.
- `401 Unauthorized` — missing or invalid authentication only. The auth dependency raises this; do not raise it yourself for forbidden actions.
- `403 Forbidden` — authenticated but not allowed (wrong role, not a collaborator).
- `404 Not Found` — resource doesn't exist, _or_ exists but the requester shouldn't know it exists. Prefer 404 over 403 to avoid leaking enumeration.
- `409 Conflict` — state conflict (duplicate creation, draft already sending, racing writes).
- `422 Unprocessable Entity` — request is syntactically valid but semantically invalid ("weekly schedule without day_of_week", "broadcasts level on a non-Post resource", "can't close a reply comment"). FastAPI returns 422 for Pydantic validation failures by default; raise it explicitly for business-rule rejections.

Reserve 400 for true malformed-input cases that FastAPI surfaces automatically. Don't use it for "your request makes no sense in the current state" — that's 422 (semantics) or 409 (state conflict).

## List responses must use an envelope

Every list endpoint returns an envelope, never a bare `list[...]`:

```python
class CommentMarkListResponse(PaginatedResponse):
    comments: list[CommentMarkResponse]
```

- `PaginatedResponse` (in `app/routers/api/schemas.py`) supplies `next_cursor: str | None` and `has_more: bool`, both defaulted for the unpaginated case. Inherit from it.
- The resource list lives under a **named field** (`comments`, `goals`, `subscriptions`) — never a generic `items`. Clients destructure by name.
- Per-resource metadata (e.g. `channel_topic_id`, `synced_at`) goes on the subclass alongside the list.
- Mirror on the client: `PaginatedResponse` is also defined in `app/javascript/react/shared/types.ts`. TS interfaces for list responses extend it.

Why: clients can write a single uniform list-response handler, and we can add pagination to any list without breaking consumers.

## DELETE returns 204 No Content

`DELETE` endpoints return `204 No Content` with no body. Clients must not read the response body.

```python
@router.delete("/workspaces/{workspace_id}/subscription", status_code=status.HTTP_204_NO_CONTENT)
async def api_workspace_subscription_delete(...):
    await Subscription.filter(...).delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- Import `from fastapi.responses import Response` and return `Response(status_code=204)` explicitly (FastAPI does not suppress a body unless you do this).
- If a DELETE has side effects that clients need to observe (e.g. a chat morphing into a DM), broadcast them over WebSocket. Do not smuggle them in the response body.
- After a DELETE, clients that need updated state should issue a follow-up GET, not parse the DELETE response.

## State transitions are named actions, not attribute writes

Split mutations by what they actually do:

- **`PATCH` the resource** when the caller hands you a value and you persist it — `content`, `title`, `owner_id`. The server records what it was told; there's no business logic beyond saving.
- **`POST /resource/{id}/<verb>`** when the change _runs business logic or side effects_ — recording an event, broadcasting to views, kicking off downstream work. The verb names the transition. This mirrors Stripe (`POST /charges/{id}/capture`, `POST /invoices/{id}/finalize`) and GitHub (close an issue).

```python
# ✓ attribute write — PATCH, caller supplies the value
PATCH /api/goals/{id}                            { "title": "Q3 launch" }

# ✓ state transitions — named, symmetric actions (see app/routers/api/mailbox_entries.py)
POST  /api/mailbox_entries/{id}/archive
POST  /api/mailbox_entries/{id}/unarchive
```

- **Name both directions symmetrically** — `/archive` _and_ `/unarchive`, `/snooze` _and_ `/unsnooze`, never one endpoint that flips based on current state. That's what "no implicit toggles" forbids: each action is explicit and idempotent (calling `/archive` twice is a no-op, not an unarchive).
- A transition that touches several records or fires events should run inside the workspace event recording / broadcast machinery — e.g. `POST /api/goals/{id}/close` records an event, records a visit, and rebroadcasts the affected views — that's the whole reason it isn't a bare PATCH.
- Mixed edits are fine where they genuinely co-occur: the comment `PATCH` carries both `content` and `resolved` because the editor saves them together (`app/routers/api/goal_comments.py`). When in doubt, ask whether the change is "save this value" (PATCH) or "do this thing" (named action).

## User settings are not a resource

There is no `/api/settings` (or `/api/users/me/settings`) bag. "Settings" is a UI grouping — the settings page aggregates many domains — not an API resource. A setting lives on the **domain resource it configures**, and the settings page composes those (the React island fetches per section, mirroring this split):

- Notification preferences → the notifications resource.
- A calendar/Slack/Notion/Gmail connection → that integration's resource (`/api/users/me/calendar`, `/api/integrations/{name}/connection`).
- Identity (name, bio, avatar) → `/api/users/me/profile`.

The exception is a setting that configures **no** domain — something user-level like timezone, locale, or theme. A lone one rides on an existing `/api/users/me/*` sub-resource (`time_zone` rides on `/api/users/me/profile` today); when several accumulate they earn their own `/api/users/me/<name>` sub-resource — pick that name when it exists, don't coin one now. Per-user sub-resources always live under `/api/users/me/<thing>` (see `/api/users/me/calendar`), never at the top level.

## Read state

Per-user, per-workspace read state ("unread", "last seen", "what's new") goes through the `Visit` model and the shared `POST /api/workspaces/{id}/visits` endpoint. Do not add a parallel read-state store or a per-resource visits endpoint. See the Visit tracking section in `CLAUDE.md`.
