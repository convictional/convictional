"""Notifications test harness.

Executable form of `docs/notifications-spec.md`. Tests express expectations as
`(resource, event, persona, prefs) -> (inbox outcome, push outcome)`, in vocabulary
that does not depend on how the notification internals are structured:

  - inbox outcome is read from the `MailboxEntry` rows (the durable surface a user sees)
  - push outcome is read from the push ledger (`Notification` rows on the PUSH channel)

The ONLY code coupled to the current system is the `emit_*` adapter below — it makes a
product event happen by driving the real HTTP API, exactly as a user would. Jobs run
inline within the request (JobsMiddleware → InlineJobs), so both surfaces are fully
materialized by the time the request returns. A rework of the notification internals
(Notifier / SubscriberResolver / NotificationPolicy / InboxUpdate) leaves every test
untouched; only this adapter — or nothing at all, since it only speaks HTTP — moves.
"""

from enum import StrEnum

from app.models.accounts import User
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Notification
from app.models.workspaces.goals import Goal
from app.models.workspaces.posts import Post
from config.enums import DeliveryChannel, GoalStatus
from tests.helpers.app import AppClient


class Inbox(StrEnum):
    """Observable inbox state for a recipient after an event.

    Collapses the `InboxUpdate` enum to what a user can actually see: both
    MARK_UNREAD and MARK_UNREAD_FORCED present a row as unread (they differ only in
    whether the reach gate was bypassed, which the persona already encodes).
    """

    UNREAD = "unread"  # row present + unread  (MARK_UNREAD / MARK_UNREAD_FORCED)
    READ = "read"  # row present, not unread  (REFRESH_CONTENT / sender's own row)
    ABSENT = "absent"  # no row  (IGNORE)


class Push(StrEnum):
    SEND = "send"
    NONE = "none"


# Named (inbox, push) outcomes, in observable terms — so an expectation block reads like
# the spec's own categories rather than a pair of raw enums.
INBOX_AND_PUSH = (Inbox.UNREAD, Push.SEND)  # mention / assignment / DM / reply-on-yours
INBOX_ONLY = (Inbox.UNREAD, Push.NONE)  # level reach
ALREADY_SEEN = (Inbox.READ, Push.NONE)  # the sender's own row — no self-alert
NOTHING = (Inbox.ABSENT, Push.NONE)  # below level / not reached


async def inbox_outcome(resource, user: User) -> Inbox:
    # The row's *current* state. Each test fires one event, so this is that event's
    # result; a multi-event test would read the final state after all of them.
    entry = await MailboxEntry.get_or_none(owner_id=user.id, resource_gid=str(resource.global_id))
    if entry is None:
        return Inbox.ABSENT
    return Inbox.UNREAD if entry.is_unread else Inbox.READ


async def push_outcome(user: User) -> Push:
    # Whether the user got *any* push this test. Correct because each test fires a single
    # event against a fresh DB; a multi-event test would have to scope this by event_id.
    delivered = await Notification.filter(
        channel=DeliveryChannel.PUSH, user_id=user.id, device_id__isnull=False
    ).exists()
    return Push.SEND if delivered else Push.NONE


async def outcomes(resource, personas: dict[str, User]) -> dict[str, tuple[Inbox, Push]]:
    return {key: (await inbox_outcome(resource, user), await push_outcome(user)) for key, user in personas.items()}


def assert_outcomes(expected: dict[str, tuple[Inbox, Push]], actual: dict[str, tuple[Inbox, Push]]) -> None:
    """Assert every persona's (inbox, push) and report ALL mismatches at once, so a
    run surfaces the full set of diverging cells rather than the first failure."""
    lines = [
        f"  {key:20} expected {exp[0].value:7}/{exp[1].value:5}  got {actual[key][0].value:7}/{actual[key][1].value:5}"
        for key, exp in expected.items()
        if actual[key] != exp
    ]
    assert not lines, "notification outcome mismatches (persona → inbox/push):\n" + "\n".join(lines)


#
# Adapter — the only code bound to the current system. Drives the real HTTP API as the
# acting user; background jobs run inline before the request returns.
#


async def emit_post_created(
    client: AppClient, actor: User, *, title: str = "All hands", content: str = "Big news", group_id=None
) -> Post:
    body: dict = {"title": title, "content": content}
    if group_id is not None:
        body["group_id"] = str(group_id)
    with client.current_user_as(actor):
        resp = await client.post("/api/posts", json=body)
    assert resp.status_code == 201, resp.text
    return await Post.get(id=resp.json()["id"])


async def emit_post_commented(
    client: AppClient, post: Post, actor: User, *, content: str = "what do you think?", parent_id: str | None = None
) -> str:
    """Fire a post comment; pass `parent_id` to reply to an existing top-level comment.
    Returns the new comment's id so a caller can thread a reply onto it."""
    body: dict = {"content": content}
    if parent_id is not None:
        body["parent_id"] = parent_id
    with client.current_user_as(actor):
        resp = await client.post(f"/api/posts/{post.id}/comments", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def emit_assigned(client: AppClient, resource, actor: User, assignee: User) -> None:
    with client.current_user_as(actor):
        resp = await client.patch(
            f"/api/workspaces/{resource.workspace_id}/assignment", json={"user_id": str(assignee.id)}
        )
    assert resp.status_code == 200, resp.text


async def emit_mailbox_archive(client: AppClient, resource, actor: User) -> None:
    """Archive the actor's own mailbox row for a resource, as tapping archive in the inbox
    would. Reads the row id, then drives the real action endpoint as the actor."""
    entry = await MailboxEntry.get(owner_id=actor.id, resource_gid=str(resource.global_id))
    with client.current_user_as(actor):
        resp = await client.post(f"/api/mailbox_entries/{entry.id}/archive")
    assert resp.status_code == 204, resp.text


async def emit_chat_message(client: AppClient, chat, actor: User, *, content: str = "hey team") -> None:
    with client.current_user_as(actor):
        resp = await client.post(f"/api/chats/{chat.id}/messages", json={"content": content})
    assert resp.status_code == 201, resp.text


async def emit_email_thread_comment(
    client: AppClient, thread, actor: User, *, content: str = "thoughts?", reply_to_id: str | None = None
) -> str:
    """Fire a thread comment; pass `reply_to_id` to reply to an existing comment.
    Returns the new comment's id so a caller can thread a reply onto it."""
    body: dict = {"content": content}
    if reply_to_id is not None:
        body["reply_to_id"] = reply_to_id
    with client.current_user_as(actor):
        resp = await client.post(f"/api/email_threads/{thread.id}/comments", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def emit_goal_commented(
    client: AppClient, goal: Goal, actor: User, *, content: str = "what do you think?", parent_id: str | None = None
) -> str:
    """Fire a goal comment; pass `parent_id` to reply to an existing top-level comment.
    Returns the new comment's id so a caller can thread a reply onto it."""
    body: dict = {"content": content}
    if parent_id is not None:
        body["parent_id"] = parent_id
    with client.current_user_as(actor):
        resp = await client.post(f"/api/goals/{goal.id}/comments", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def emit_goal_update_posted(
    client: AppClient, goal: Goal, actor: User, *, status: GoalStatus = GoalStatus.ON_TRACK, answer: str = "on track"
) -> None:
    with client.current_user_as(actor):
        resp = await client.post(
            f"/api/goals/{goal.id}/updates",
            json={"status": status.value, "question_text": "How's it going?", "answer_text": answer},
        )
    assert resp.status_code == 201, resp.text


async def emit_goal_update_requested(client: AppClient, goal: Goal, actor: User) -> None:
    """`actor` requests a status update; it is always asked of the goal's owner (who authors it)."""
    with client.current_user_as(actor):
        resp = await client.post(
            f"/api/goals/{goal.id}/updates/request",
            json={"question_text": "Can you post an update?"},
        )
    assert resp.status_code == 201, resp.text


async def emit_goal_closed(client: AppClient, goal: Goal, actor: User, *, is_completed: bool) -> None:
    """Close the goal — completed (`GOAL_COMPLETED`) or abandoned (`GOAL_CLOSED`)."""
    with client.current_user_as(actor):
        resp = await client.post(f"/api/goals/{goal.id}/close", json={"is_completed": is_completed})
    assert resp.status_code == 200, resp.text


async def emit_goal_edited(client: AppClient, goal: Goal, actor: User, *, title: str) -> None:
    """A minor content revision (a title edit) — a `GOAL_UPDATED` field edit."""
    with client.current_user_as(actor):
        resp = await client.patch(f"/api/goals/{goal.id}", json={"title": title})
    assert resp.status_code == 200, resp.text


async def emit_mailbox_mark_read(client: AppClient, resource, actor: User) -> None:
    """Mark the actor's own mailbox row read, as opening the item in the inbox would. Tolerates
    a missing row: until goals are inbox-native they create no row, so a read precondition is a
    no-op — the row it would mark simply doesn't exist yet."""
    entry = await MailboxEntry.get_or_none(owner_id=actor.id, resource_gid=str(resource.global_id))
    if entry is None:
        return
    with client.current_user_as(actor):
        resp = await client.post(f"/api/mailbox_entries/{entry.id}/mark_read")
    assert resp.status_code == 204, resp.text
