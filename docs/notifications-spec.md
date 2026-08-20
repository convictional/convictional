# Notifications spec

This is the specification for what notifications the app is supposed to produce. It is
written to be **independent of how the code is currently structured** — inputs are
product events and audience relationships, outputs are observable deliveries. The
current implementation (`Notifier`, `SubscriberResolver`, `NotificationPolicy`,
`InboxUpdate`, the various jobs) is expected to be reworked; this document is the
contract that rework must satisfy, and the source of truth for the test suite.

The vocabulary here is deliberately only what already exists in the product or the code:
subscription **levels** from the settings page (`ALL` / `BROADCASTS` / `RELEVANT_ONLY`),
the inbox outcome enum `InboxUpdate` (`MARK_UNREAD_FORCED` / `MARK_UNREAD` /
`REFRESH_CONTENT` / `IGNORE`), push `send` / `none`, and the settings page's own phrase
"**always reaches you**". The one term this doc adds is **tie** — a recipient's personal
connection to a thread (having commented in it), defined in supporting rule 5.

## Scope: two surfaces

The notifications system owns exactly two surfaces:

1. **Inbox** — the durable "needs my attention" surface, rendered as a native inbox UI.
2. **Push** — an ephemeral, opt-in, real-time alert layered on top.

**Email is out of scope.** Email is a special-case delivery exception, not part of the
notifications system. Goals, documents, and meetings currently deliver via email *only*
because their native inbox UI has not been built yet — a legacy exception, not modeled
here. Do not add email as an output column.

The **near-term executable suite** covers the three resources with a real inbox surface
today: **Chat, Post, EmailThread**. Goals/Documents/Meetings appear below as *intended*
behavior with inbox marked pending.

## The rules

Inbox and push resolve independently for each event and recipient.

**Inbox.** An event is forced into your inbox (`MARK_UNREAD_FORCED`, overriding your level
and any mute) when it **always reaches you** — a mention, an assignment / direct ask, a
DM, or a **reply on yours** (supporting rule 5). Otherwise it lands by your
**level**: `MARK_UNREAD` at `ALL` (or a matching `BROADCASTS` post), `IGNORE` below.

**Push.** Push fires for exactly two things, and nothing else:

- a **mention, an assignment / direct ask, or a reply on yours** (supporting rule 5) —
  on any resource; or
- a message in a **direct chat you belong to** — a DM (always, since a DM can't be
  unsubscribed) or a multi-person direct chat while subscribed at `ALL` (muting silences
  it).

Group channels and all broadcast/subscription content (posts, goals, documents, email
threads) never push.

## Supporting rules

1. **Actor / self.** The actor gets no self-alert for the event they triggered. If they are
   already reached (or already have a row) that row is `REFRESH_CONTENT`, no push; an actor
   below reach with no row gets nothing — acting on a resource does not manufacture a row.
   Exception: a **self-mention or self-assignment** always reaches you and behaves exactly as
   if someone else did it.
2. **Mute narrows the inbox.** A group mute drops the member `ALL`→`RELEVANT_ONLY` for
   that group's items on the inbox surface. Because level-based reach is already silent, a
   mute only affects push in the one place level-based reach pushes — a **multi-person
   direct chat**, where muting silences it. Things that always reach you (mentions,
   replies on your stuff, etc.) still reach you regardless of a mute.
3. **`BROADCASTS` level** = `ALL` for org-wide items, `RELEVANT_ONLY` otherwise. A
   per-resource capability (Post today; may extend to meetings/documents), not a Post-only
   hardcode.
4. **Timing is a separate layer.** Push working hours gate delivery of an otherwise
   eligible push — they change *whether/when it arrives*, not *who is eligible*. This is
   the only timing layer (email batching left scope with email).
5. **"Reply on yours" spans the resource *and* the thread.** A new comment always reaches
   you (inbox + push, ignoring your level and any mute — exactly like a mention) when it
   lands *either*:
   - on a **resource you created or are assigned to** (you own the post/goal/document/
     thread the comment hangs off), *or*
   - in a **comment thread you've already commented in** — someone replying to your
     comment reaches you even when you don't own the resource and are below `ALL`.

   "Thread" is the resource's existing grouping, not a new concept: `parent_id` root
   (Post, Goal), `comment_mark_id` annotation (Document), `reply_to` chain (EmailThread).
   Participation is authorship — you've posted at least one comment in that thread; passive
   viewers and reactors are not participants. This is a *tie* to the thread: a
   `RELEVANT_ONLY` subscriber with a tie is reached, one without a tie is not.

   Resolving a thread does not opt you out: a reply reopens the conversation and still
   reaches prior participants (the thread lookup ignores `resolved_at`).

## Surface eligibility per resource

| Resource | Inbox | Default level | `BROADCASTS` level | Push on level-based reach? |
|---|---|---|---|---|
| **Chat** | ✅ native | `ALL` | no | only multi-person direct chat (at `ALL`) |
| **Post** | ✅ native | `BROADCASTS` | yes | no |
| **EmailThread** | ✅ native | `RELEVANT_ONLY` | no (today) | no |
| **Goal** | ⏳ pending (legacy email, out of scope) | `RELEVANT_ONLY` | future candidate | no |
| **Document** | ⏳ pending | `RELEVANT_ONLY` | future candidate | no |
| **Meeting** | ⏳ pending | `RELEVANT_ONLY` | future candidate | no |

Mentions, assignments, DMs, and replies-on-your-stuff push on **every** resource; the
column above is only about push driven by subscription level.

Goal / Document / Meeting have no inbox surface yet, so email is their only channel today.
Email is out of scope for this spec, but that legacy email behavior (who gets emailed on
a goal/document comment or a meeting agenda update) is protected by a quarantined suite,
`tests/integration/notifications/test_legacy_email.py` — to be deleted once these
resources move onto the inbox.

## Worked matrices

`actor` excluded throughout (supporting rule 1). Push cells assume push-on + device
present + within working hours; the timing layer can still suppress an otherwise-`send`.
The "reason" column names why the outcome holds, in product terms.

### Post

| Event → persona | reason | inbox | push |
|---|---|---|---|
| **post_commented** → creator | reply on yours (resource) | `MARK_UNREAD_FORCED` | send |
| post_commented → assignee | reply on yours (resource) | `MARK_UNREAD_FORCED` | send |
| post_commented → thread participant@`RELEVANT_ONLY` (has tie) | reply on yours (thread) | `MARK_UNREAD_FORCED` | send |
| post_commented → mentioned | mention | `MARK_UNREAD_FORCED` | send |
| post_commented → subscriber@`ALL` | level reach | `MARK_UNREAD` | none |
| post_commented → group-member (unmuted) | level reach | `MARK_UNREAD` | none |
| post_commented → muted group-member | level reach (muted) | `REFRESH_CONTENT` if a row exists, else `IGNORE` | none |
| post_commented → subscriber@`RELEVANT_ONLY` (no tie) | below level, no thread tie | `IGNORE` | none |
| **assigned** → assignee | assignment | `MARK_UNREAD_FORCED` | send |
| assigned → creator | level reach (`ALL` on own post) | `MARK_UNREAD` | none |
| **post_created** → group-member | level reach | `MARK_UNREAD` | none |
| post_created → subscriber@`BROADCASTS` (org-wide post) | level reach | `MARK_UNREAD` | none |
| post_created → subscriber@`BROADCASTS` (group post, not a member) | below level | `IGNORE` | none |
| **post_announced** → org-member | force-notify | `MARK_UNREAD_FORCED` | none¹ |
| post_announced → mentioned | mention | `MARK_UNREAD_FORCED` | send |
| **post_decided** → creator/assignee | reply on yours (resource) | `MARK_UNREAD_FORCED` | send |
| **content revision** (edit/delete) → anyone with a row | revision | `REFRESH_CONTENT` | none |

¹ Announcements force every member's inbox (so everyone reads them eventually) but do not
qualify for push on their own; only an @mention inside the announcement pushes.

### Chat

| Event → persona | reason | inbox | push |
|---|---|---|---|
| **1:1 DM message** → recipient | DM | `MARK_UNREAD_FORCED` | send |
| **multi-person direct message** → subscriber@`ALL` | direct chat (level inbox, pushes) | `MARK_UNREAD` | send |
| multi-person direct message → member who muted (`RELEVANT_ONLY`) | level reach (muted) | `REFRESH_CONTENT` / `IGNORE` | none |
| multi-person direct message → mentioned | mention | `MARK_UNREAD_FORCED` | send |
| **group-channel message** → subscriber@`ALL` | level reach | `MARK_UNREAD` | none |
| group-channel message → mentioned | mention | `MARK_UNREAD_FORCED` | send |
| group-channel message → subscriber@`RELEVANT_ONLY` (no tie) | below level | `IGNORE` | none |
| **content revision** (edit/delete) → anyone with a row | revision | `REFRESH_CONTENT` | none |
| **collaborator added** → added user | added you² | `MARK_UNREAD_FORCED` | send² |

² Being added is a personal action; treated as always-reaches-you. Confirm you want it to
push (vs. force-inbox only).

### EmailThread

Email threads set `force_include_all_collaborators_for_inbox` — **every collaborator
lands in the inbox regardless of level** ("Email always arrives in your inbox"). So level
does not gate the email-thread inbox; the only inbox distinction is collaborator vs. not.
Reply-on-yours (creator/assignee/tied) is `MARK_UNREAD_FORCED` here as everywhere — the
distinction from plain force-include `MARK_UNREAD` only shows on a thread you've archived
(see below).

| Event → persona | reason | inbox | push |
|---|---|---|---|
| **comment** → creator | reply on yours (resource) | `MARK_UNREAD_FORCED` | send |
| comment → assignee | reply on yours (resource) | `MARK_UNREAD_FORCED` | send |
| comment → mentioned | mention | `MARK_UNREAD_FORCED` | send |
| comment → thread participant @`RELEVANT_ONLY` (has tie) | reply on yours (thread) | `MARK_UNREAD_FORCED` | send |
| comment → collaborator @`ALL` | force-include | `MARK_UNREAD` | none |
| comment → collaborator @`RELEVANT_ONLY` (no tie) | force-include (level doesn't gate email inbox) | `MARK_UNREAD` | none |
| comment → non-collaborator | not in the thread | `IGNORE` | none |
| **inbound mail publish** → collaborators | force-include³ | `MARK_UNREAD` | none |
| **content revision** (edit/delete) → anyone with a row | revision | `REFRESH_CONTENT` | none |

³ Inbound email is thread activity (inbox for collaborators, no push), even for the
assignee — a new external email is not a "reply on your stuff" in the comment sense.
Not yet covered by the executable suite (no HTTP path; inbound mail is model-simulated).

**Archived threads and "reply on yours."** A reply that always reaches you (`MARK_UNREAD_FORCED`
— reply on your own thread, a reply in a thread you're tied to, or a mention) **re-surfaces an
archived row into the inbox**; it does not merely refresh the archived row's content. The two
surfaces stay consistent: anything worth a push is worth being back in the inbox. This holds
even when the thread is archived in Gmail — a directed reply overrides the Gmail gate the same
way a mention does. Plain force-include activity (`MARK_UNREAD` — a collaborator reached only by
level) does *not* re-surface a thread you archived. This is the one case where the
archived-vs-inbox distinction is load-bearing, so the suite reads the inbox surface (the `INBOX`
label), not just the unread flag: a row that stays archived is neither surfaced nor unread on
the inbox surface even if its content refreshes.

## Test suite shape (how this doc becomes tests)

- **The suite encodes desired behavior, not current behavior.** A failing test means fix
  the code, not the test. Where the code is known to lag this spec, that gap lives as an
  `xfail(strict=True)` test — executable, and it flips to a failure the moment the code
  catches up, so it can't silently rot the way a hand-maintained list would.
- Cells are expressed in the vocabulary above: `(resource, event, persona, prefs) →
  (InboxUpdate outcome, push send/none)`.
- A single thin **adapter** binds a cell to the current code: it makes the product event
  happen at the domain-action level and reads the two surfaces from the fake push sink
  and the `MailboxEntry` rows. No test touches the internal decision functions.
- A refactor of the notifications internals rewrites only the adapter; the test cells
  keep their meaning.
