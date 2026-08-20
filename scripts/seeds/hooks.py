import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from app.helpers.strings import html_to_plain_text
from app.models.accounts import User
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.workspace import (
    Collaborator,
    Decision,
    Event,
    LinkPreview,
    SubscriptionPreference,
)
from app.models.workspaces.chat import ChatMessage
from app.models.workspaces.documents import Document
from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.thread import EmailMessage, EmailThread, EmailThreadComment
from app.models.workspaces.goals import Goal, GoalComment, GoalUpdate
from app.models.workspaces.meetings import Meeting, MeetingAttendee
from app.models.workspaces.posts import Post, PostComment
from app.presenters.link_previews import prepare_link_preview_for_comment
from config.enums import EmailLabel, EmailMessageType, EventAction, MeetingAttendeeStatus, Sharing
from infra.db import RecordModel
from infra.storage import TrustedBytesIO, store_file
from scripts.seeds.content_seeder import Attendee, ResourceRef
from scripts.seeds.seeder import Ref, after_create, before_create, create

MENTION_PATTERN = r"@\[([^\]]+)\]"


def register():
    pass


#
# Before Create
#
#


@before_create(Document)
async def _prepare_document(kwargs, meta, **_):
    if "content" in kwargs:
        meta["live_document_body"] = kwargs.pop("content")


@before_create(Post)
async def _publish_post(kwargs, **_):
    if "published_at" not in kwargs:
        kwargs["published_at"] = datetime.now(UTC)


@before_create(Meeting)
async def _prepare_meeting(kwargs, **_):
    if "content" in kwargs:
        kwargs["transcript"] = kwargs.pop("content")

    if "attendees" in kwargs and kwargs["attendees"] and isinstance(kwargs["attendees"][0], Attendee):
        result = []
        for a in kwargs["attendees"]:
            user_id = a.user.id
            user = await User.get(id=user_id)
            result.append(
                MeetingAttendee(
                    user_id=user_id,
                    name=user.name,
                    status=MeetingAttendeeStatus.ACCEPTED,
                    is_organizer=a.is_organizer,
                )
            )
        kwargs["attendees"] = result

    if "duration_minutes" in kwargs:
        duration = kwargs.pop("duration_minutes")
        if "scheduled_at" in kwargs and "scheduled_end_at" not in kwargs:
            kwargs["scheduled_end_at"] = kwargs["scheduled_at"] + timedelta(minutes=duration)


@before_create(EmailThreadComment)
async def _prepare_comment(kwargs, **_):
    if "email_thread" in kwargs:
        ref = kwargs.pop("email_thread")
        thread = await EmailThread.get(id=ref.id)
        kwargs["email_thread_id"] = thread.id


@before_create(EmailMessage)
async def _ensure_email_thread(kwargs, **_):
    thread_ref = kwargs.get("thread")
    if not isinstance(thread_ref, Ref):
        return

    thread_id = thread_ref.id
    if await EmailThread.exists(id=thread_id):
        return

    creator_id = kwargs["user"].id
    org = kwargs["organization"]
    org_id = org.id if isinstance(org, RecordModel) else org

    await EmailThread.create(
        id=thread_id, title="", creator_id=creator_id, organization_id=org_id, sharing=Sharing.PRIVATE
    )


@before_create(PostComment)
async def _strip_decision_flag(kwargs, meta, **_):
    if "is_decision_comment" in kwargs:
        meta["is_decision"] = bool(kwargs.pop("is_decision_comment"))


@before_create(GoalComment, PostComment, EmailThreadComment, ChatMessage)
async def _prepare_reactions(kwargs, **_):
    if "reactions" not in kwargs:
        return
    resolved = {}
    for key, users in kwargs["reactions"].items():
        rtype = key.lower()
        resolved[rtype] = [Ref(u).id if isinstance(u, str) else u for u in users]
    kwargs["reactions"] = resolved


@before_create(GoalUpdate)
async def _prepare_goal_update(kwargs, **_):
    if "content" in kwargs:
        kwargs["answer_text"] = kwargs.pop("content")
    kwargs.setdefault("is_completed", True)
    if "completed_at" not in kwargs:
        kwargs["completed_at"] = datetime.now(UTC)


@before_create(EmailMessage)
async def _prepare_email_message(kwargs, **_):
    if "content" in kwargs:
        kwargs["body_html"] = kwargs.pop("content")

    async def ref_to_address(ref: Ref) -> str:
        user = await User.get(id=ref.id)
        return str(EmailAddress(name=user.name, email=user.email))

    if isinstance(kwargs.get("sender"), Ref):
        kwargs["sender"] = await ref_to_address(kwargs["sender"])

    for addr_field in ("to", "cc", "bcc"):
        if addr_field in kwargs and isinstance(kwargs[addr_field], list):
            kwargs[addr_field] = [
                await ref_to_address(item) if isinstance(item, Ref) else item for item in kwargs[addr_field]
            ]

    if "body_html" in kwargs:
        body_plain = html_to_plain_text(kwargs["body_html"])
        kwargs["body_plain"] = body_plain
        kwargs["preview"] = body_plain[:150].replace("\n", " ").strip()

    if "labels" not in kwargs:
        if kwargs["message_type"] == EmailMessageType.RECEIVED:
            kwargs["labels"] = [EmailLabel.INBOX, EmailLabel.UNREAD]
        elif kwargs["message_type"] == EmailMessageType.SENT:
            kwargs["labels"] = [EmailLabel.SENT]

    if "resource_ref" in kwargs:
        resource_ref: ResourceRef = kwargs.pop("resource_ref")
        headers = kwargs.get("headers_list") or []
        headers.append({"name": "X-Convictional-GID", "value": resource_ref.gid.to_param})
        kwargs["headers_list"] = headers


#
# After Create
#
#


@after_create(Document)
async def _set_document_body(instance, meta, **_):
    body = meta.get("live_document_body")
    if body:
        await LiveDocument.set_initial_content(instance.live_document_topic, body)


@after_create(User)
async def _setup_user(instance, **_):
    await SubscriptionPreference.ensure_defaults(instance.id)
    await instance.mark_onboarding_mailbox_sync_complete()


@after_create(User)
async def _set_avatar(instance, key, namespace, **_):
    avatars_dir = Path(__file__).parent / namespace / "avatars"
    png = avatars_dir / f"{key}.png"
    if not png.exists():
        return

    file_ref = await store_file(TrustedBytesIO(png.read_bytes()), "avatar.png", "image/png")

    instance.avatar_file_id = file_ref.id
    await instance.save(update_fields=["avatar_file_id"])


_recording_cache: dict[str, UUID] = {}


@after_create(Meeting)
async def _set_recording(instance, namespace, **_):
    if instance.scheduled_at and instance.scheduled_at > datetime.now(UTC):
        return

    if namespace in _recording_cache:
        instance.recording_id = _recording_cache[namespace]
        await instance.save(update_fields=["recording_id"])
        return

    recording_path = Path(__file__).parent / namespace / "assets" / "meeting_recording.mp4"
    if not recording_path.exists():
        return

    file_ref = await store_file(TrustedBytesIO(recording_path.read_bytes()), "recording.mp4", "video/mp4")
    _recording_cache[namespace] = file_ref.id
    instance.recording_id = file_ref.id
    await instance.save(update_fields=["recording_id"])


@after_create(EmailThreadComment)
async def _on_comment(instance, merged, **_):
    thread = await EmailThread.get(id=instance.email_thread_id)
    workspace_id = thread.workspace_id
    await Collaborator.get_or_create(
        workspace_id=workspace_id,
        user_id=instance.user_id,
        defaults={"added_by_id": instance.user_id},
    )

    mentioned_names = re.findall(MENTION_PATTERN, instance.content)
    if mentioned_names:
        for user in await User.filter(organization_id=thread.organization_id, name__in=mentioned_names):
            await Collaborator.get_or_create(
                workspace_id=workspace_id,
                user_id=user.id,
                defaults={"added_by_id": instance.user_id},
            )

    await create(
        Event,
        f"{instance.id}-event",
        workspace_id=workspace_id,
        recordable_id=instance.id,
        recordable_type="EmailThreadComment",
        action=EventAction.COMMENTED,
        creator_id=instance.user_id,
        created_at=instance.created_at,
    )


@after_create(PostComment)
async def _on_post_comment(instance, merged, **_):
    post = merged["post"]
    if isinstance(post, Ref):
        post = await Post.get(id=post.id)
    await create(
        Event,
        f"{instance.id}-event",
        workspace_id=post.workspace_id,
        recordable_id=instance.id,
        recordable_type="PostComment",
        action=EventAction.POST_COMMENTED,
        creator_id=instance.user_id,
        created_at=instance.created_at,
    )


@after_create(PostComment)
async def _unfurl_link_preview(instance, **_):
    # Seed-time unfurl hits the real web, which is flaky under CI xdist load.
    # Skip in tests; the demo still gets real previews when ENV is development.
    if os.environ.get("ENV") == "test":
        return
    if not instance.content:
        return
    author = await User.get_or_none(id=instance.user_id)
    if not author:
        return
    link_preview_data = await prepare_link_preview_for_comment(instance.content, author)
    if link_preview_data:
        await LinkPreview.associate(PostComment, instance.id, link_preview_data)


@after_create(PostComment)
async def _on_decision_comment(instance, merged, key, meta, **_):
    if not meta.get("is_decision"):
        return
    post = merged["post"]
    if isinstance(post, Ref):
        post = await Post.get(id=post.id)
    await create(
        Decision,
        f"{key}-decision",
        workspace_id=post.workspace_id,
        comment_gid=instance.global_id,
        decided_by_id=instance.user_id,
        decided_at=instance.created_at,
    )


@after_create(Goal)
async def _seed_goal_history(instance, **_):
    if instance.parent_id:
        return

    await create(
        Event,
        f"{instance.id}-created-event",
        workspace_id=instance.workspace_id,
        recordable_id=instance.id,
        recordable_type="Goal",
        action=EventAction.GOAL_CREATED,
        creator_id=instance.creator_id,
        details={"description": instance.description},
        created_at=instance.created_at,
    )

    await create(
        Event,
        f"{instance.id}-activated-event",
        workspace_id=instance.workspace_id,
        recordable_id=instance.id,
        recordable_type="Goal",
        action=EventAction.GOAL_ACTIVATED,
        creator_id=instance.creator_id,
        details={"activated": True},
        created_at=instance.created_at,
    )

    if instance.owner_id and instance.owner_id != instance.creator_id:
        await create(
            Event,
            f"{instance.id}-owner-event",
            workspace_id=instance.workspace_id,
            recordable_id=instance.id,
            recordable_type="Goal",
            action=EventAction.GOAL_UPDATED,
            creator_id=instance.creator_id,
            details={"owner_id": [None, str(instance.owner_id)]},
            created_at=instance.created_at,
        )


@after_create(GoalUpdate)
async def _on_goal_update(instance, merged, **_):
    goal = merged["goal"]
    if isinstance(goal, Ref):
        goal = await Goal.get(id=goal.id)

    details: dict[str, Any] = {"question_text": instance.question_text, "is_completed": False}
    if instance.status and instance.status.value != goal.status.value:
        details["status"] = [goal.status.value, instance.status.value]
        goal.status = instance.status
        await goal.save(update_fields=["status"])

    await create(
        Event,
        f"{instance.id}-event",
        workspace_id=goal.workspace_id,
        recordable_id=instance.id,
        recordable_type="GoalUpdate",
        action=EventAction.GOAL_UPDATE_POSTED,
        creator_id=instance.creator_id,
        details=details,
        created_at=instance.created_at,
    )


@after_create(GoalComment)
async def _on_goal_comment(instance, merged, **_):
    goal = merged["goal"]
    if isinstance(goal, Ref):
        goal = await Goal.get(id=goal.id)
    await create(
        Event,
        f"{instance.id}-event",
        workspace_id=goal.workspace_id,
        recordable_id=instance.id,
        recordable_type="GoalComment",
        action=EventAction.GOAL_COMMENTED,
        creator_id=instance.user_id,
        created_at=instance.created_at,
    )
