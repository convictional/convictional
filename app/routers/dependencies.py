import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from re import Pattern
from typing import Any, ClassVar, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.routing import iter_route_contexts
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.templating import Jinja2Templates
from google.auth.transport import requests  # type: ignore
from google.oauth2 import id_token  # type: ignore
from jinja2 import Environment
from pydantic import HttpUrl
from sse_starlette import EventSourceResponse
from starlette.datastructures import URL
from starlette.requests import HTTPConnection
from starlette.types import Receive, Scope, Send
from tortoise import BaseDBAsyncClient
from tortoise.query_utils import Prefetch

from app.channels.base import BroadcastHandler, ChannelMessage, channels
from app.channels.base import Channel as BaseChannel
from app.helpers.url import build_safe_redirect_url
from app.jobs.content import ContentIndexingJob
from app.jobs.mailers import SendNewOrganizationEmailJob, SendNewUserEmailJob
from app.middleware.csrf import rotate_csrf_token
from app.models.accounts import Group, User
from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.collaboration.workspace import (
    Attachment,
    CommentMixin,
    SubscriptionPreference,
    Workspace,
)
from app.models.workspaces.documents import Document
from app.models.workspaces.email.thread import EmailDraft, EmailMessage, EmailThread, EmailThreadComment
from app.models.workspaces.goals import Goal
from app.models.workspaces.meetings import Meeting
from app.models.workspaces.posts import Post, PostFilters
from app.organization_setup import populate_new_organization
from app.routers import API_PREFIX
from app.templates import template_variant
from config.enums import (
    ChannelEventAction,
    ChannelEventResource,
    ChannelMessageType,
    EmailMessageType,
    FlashLevel,
    Sharing,
)
from config.logging import LoggingContext, logger
from config.settings import settings
from infra.db import transaction
from infra.jobs import enqueue_job
from infra.oauth import Token

if settings.sentry_dsn:
    import sentry_sdk

DEFAULT_TIMEZONE = "UTC"
SSE_ACCEPT_HEADER = "text/event-stream"


@lru_cache(maxsize=1)
def _effective_route_tags(app: FastAPI) -> dict[int, frozenset[str]]:
    # Map each original APIRoute (the object placed in `scope["route"]`) to the
    # full set of tags it carries once router-prefix tags are merged in. Built
    # once per app via FastAPI's own route traversal; routes are fixed after
    # startup so the cache never goes stale.
    tags_by_route: dict[int, frozenset[str]] = {}
    for ctx in iter_route_contexts(app.routes):
        ctx_tags = frozenset(str(tag) for tag in (getattr(ctx, "tags", None) or []))
        key = id(ctx.original_route)
        tags_by_route[key] = tags_by_route.get(key, frozenset()) | ctx_tags
    return tags_by_route


INBOX_SORT_PREFERENCE_COOKIE = "inbox_sort_preference"
INBOX_SORT_PREFERENCE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year

# Re-coerce via HttpUrl: settings.base_url is typed HttpUrl but some test
# envs hand it back as a string, so .scheme / .host would fail otherwise.
# Same workaround as app/middleware/react_toggle.py.
_BASE_URL = HttpUrl(settings.base_url)
_COOKIE_DOMAIN = f".{_BASE_URL.host}" if settings.is_env("staging", "production") else None
_COOKIE_SECURE = _BASE_URL.scheme == "https"


def set_inbox_sort_preference_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        INBOX_SORT_PREFERENCE_COOKIE,
        value,
        max_age=INBOX_SORT_PREFERENCE_COOKIE_MAX_AGE,
        path="/",
        httponly=True,
        samesite="lax",
        domain=_COOKIE_DOMAIN,
        secure=_COOKIE_SECURE,
    )


def delete_inbox_sort_preference_cookie(response: Response) -> None:
    response.delete_cookie(
        INBOX_SORT_PREFERENCE_COOKIE,
        path="/",
        domain=_COOKIE_DOMAIN,
        secure=_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )


#
# Templates
#
#

templates = None


def register_templates(env: Environment):
    global templates
    templates = Jinja2Templates(env=env)


def get_templates():
    if not templates:
        raise RuntimeError("Templates have not been registered, call register_templates first")
    return templates


#
# Auth
#
#


class Authentication:
    connection: HTTPConnection
    current_user: User | None = None

    def __init__(self, connection: HTTPConnection):
        self.connection = connection

        # current_user can't be accepted as a parameter because of this bug:
        # https://github.com/tortoise/tortoise-orm/issues/1925
        # So create the instance and set the property if needed
        self.current_user = None

    @property
    def current_user_id(self):
        return self.connection.session.get("user_id", None)

    @property
    def is_superuser(self):
        return bool(self.current_user and self.current_user.is_superuser)

    async def has_valid_login(self):
        await self._ensure_valid_session()
        return bool(self.current_user and self.current_user.has_logged_in and not self.current_user.is_deleted)

    async def load(self):
        await self._load_current_user()

    async def _load_current_user(self):
        if self.current_user:
            await self.current_user.fetch_related("organization", "oauth_tokens", "avatar_file")
            return

        if self.current_user_id:
            user: User | None = (
                await User.nondeleted.get_queryset()
                .get_or_none(id=self.current_user_id)
                .select_related("organization", "avatar_file")
                .prefetch_related("oauth_tokens")
            )
            if user:
                self.current_user = user

    async def _ensure_valid_session(self):
        if self.current_user and self.current_user.is_deleted:
            await self.logout()

    def login(self, user: User):
        self.connection.session["user_id"] = str(user.id)
        # Per-login nonce for the cross-tab BroadcastChannel notification in csrf.ts
        # only — nothing server-side validates it (logout is scoped to the cookie).
        self.connection.session["created_at"] = datetime.now(UTC).isoformat()
        rotate_csrf_token(self.connection.session, self.connection.state)
        self.current_user = user
        return user

    async def logout(self):
        # Clearing the cookie logs out only the current device — every other device
        # holds its own independent session cookie. Account deactivation/deletion
        # blocks all devices instead, since a soft-deleted user fails the nondeleted
        # load in _load_current_user on the next request.
        self.connection.session.clear()
        rotate_csrf_token(self.connection.session, self.connection.state)
        self.current_user = None


async def get_authentication(connection: HTTPConnection):
    result = Authentication(connection)
    await result.load()

    if settings.sentry_dsn and result.current_user:
        sentry_sdk.set_user({"id": str(result.current_user.id), "email": result.current_user.email})

    if result.current_user:
        with LoggingContext(user_id=result.current_user.id, organization_id=result.current_user.organization_id):
            yield result
    else:
        yield result


async def get_current_user(
    connection: HTTPConnection,
    templates: Jinja2Templates = Depends(get_templates),
    authentication: Authentication = Depends(get_authentication),
) -> User:
    helpers = Helpers(connection=connection, templates=templates, authentication=authentication)

    if not await authentication.has_valid_login():
        helpers.remember_location()

        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail="Redirecting to login",
            headers={"location": str(helpers.url_for("login"))},
        )

    assert authentication.current_user is not None  # This is a type hint for mypy, it should never be None here

    await backfill_user_timezone(authentication.current_user, connection)

    if not helpers.is_xhr:
        await authentication.current_user.mark_seen()
    return authentication.current_user


async def backfill_user_timezone(user: User, connection: HTTPConnection) -> None:
    # The browser sets a `timezone` cookie on every page load (app/javascript/main.ts). Persist it to
    # user.time_zone the first time we see an authenticated request from a user without one, so
    # downstream features (scheduled research crons, formatted timestamps) have a real zone to work with
    # instead of falling back to UTC.
    if user.time_zone:
        return
    cookie_tz = connection.cookies.get("timezone")
    if not cookie_tz:
        return
    try:
        ZoneInfo(cookie_tz)
    except (ZoneInfoNotFoundError, ValueError):
        return
    user.time_zone = cookie_tz
    await user.save(update_fields=["time_zone", "updated_at"])


async def get_superuser(authentication: Authentication = Depends(get_authentication)):
    if not authentication.current_user or not authentication.current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return authentication.current_user


async def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return current_user


async def get_or_create_user(authentication: Authentication, token: Token):
    if not token.id_token_model.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email not found in response.")

    user, is_new_login, is_new_organization, _ = await User.get_or_create_by_oauth(token)
    authentication.login(user)
    await user.mark_login()

    if is_new_login:
        await SubscriptionPreference.ensure_defaults(user.id)
        await enqueue_job(ContentIndexingJob.from_model(user.organization_id, user))
        # First login, not account creation, is the "new user" signal: an invite pre-creates the
        # account, so is_new_login covers both direct signups and invited users accepting.
        await enqueue_job(SendNewUserEmailJob(user_id=user.id))

    if is_new_organization:
        await user.make_admin()
        async with transaction() as connection:
            await populate_new_organization(user, using_db=connection)
        await enqueue_job(SendNewOrganizationEmailJob(organization_id=user.organization_id))

    return user


#
# Exceptions
#
#


class RequestAccessError(Exception):
    def __init__(self, global_id: str) -> None:
        self.global_id = global_id


#
# Background Jobs
#
#

job_security = HTTPBearer()


def verify_job_token(auth: HTTPAuthorizationCredentials = Depends(job_security)):
    if settings.enable_fake_auth:
        return True

    token = auth.credentials
    if not token:
        logger.warning("No token provided for background job")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized background job request")

    # The new audience should be jobs_service_url for the jobs service
    migrated_audience = str(settings.jobs_service_url)

    # The fallback audience is the old method
    fallback_audience = str(settings.base_url)

    try:
        # Try with the primary audience first
        id_token.verify_oauth2_token(token, requests.Request(), audience=migrated_audience)
        return True
    except ValueError as e:
        # If we have a fallback and it's different from primary, try that.
        # TODO remove this after migration is completed.
        if fallback_audience != migrated_audience:
            try:
                id_token.verify_oauth2_token(token, requests.Request(), audience=fallback_audience)
                logger.info("Job authenticated with fallback audience")
                return True
            except ValueError:
                pass

        logger.warning(f"Error authenticating background job: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Error authenticating background job")


#
# Models
#
#


async def get_org_users(current_user: User = Depends(get_current_user)):
    users = (
        await User.active.get_queryset()
        .filter(organization_id=current_user.organization_id)
        .select_related("avatar_file")
        .all()
    )
    return users


async def get_goal(goal_id: UUID, current_user: User = Depends(get_current_user)) -> Goal:
    result: Goal = await (
        Goal.get(id=goal_id, organization_id=current_user.organization_id)
        .select_related("owner", "group", "workspace")
        .prefetch_related(Prefetch("subgoals", queryset=Goal.all().select_related("owner", "group")))
    )
    return result


workspace_context: ContextVar[Workspace | None] = ContextVar("workspace_context", default=None)


async def get_workspace(workspace_id: UUID, current_user: User = Depends(get_current_user)):
    result = await Workspace.get(id=workspace_id, organization_id=current_user.organization_id).prefetch_related(
        "collaborators__user"
    )
    await result.fetch_resource()

    if not result.resource.collaboration.can_be_accessed_by(current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    workspace_context.set(result)
    return result


async def index_workspace_resource(request: Request):
    yield
    if request.method.lower() in ["post", "put", "patch", "delete"]:
        if workspace := workspace_context.get():
            await enqueue_job(ContentIndexingJob.from_model(workspace.resource.organization_id, workspace.resource))


post_context: ContextVar[Post | None] = ContextVar("post_context", default=None)


def create_post_indexer(
    skip_paths: list[Pattern] = [],
) -> Callable[[Request], AsyncGenerator[None]]:
    async def _index_post(request: Request):
        yield
        if request.method.lower() in ["post", "put", "patch", "delete"] and not any(
            [path.match(request.url.path) for path in skip_paths]
        ):
            if post := post_context.get():
                await enqueue_job(ContentIndexingJob.from_model(post.organization_id, post))

    return _index_post


email_thread_comment_context: ContextVar[EmailThreadComment | None] = ContextVar(
    "email_thread_comment_context", default=None
)


def create_email_thread_comment_indexer(
    skip_paths: list[Pattern] = [],
) -> Callable[[Request], AsyncGenerator[None]]:
    async def _index_email_thread_comment(request: Request):
        yield
        if request.method.lower() in ["post", "put", "patch", "delete"] and not any(
            [path.match(request.url.path) for path in skip_paths]
        ):
            if comment := email_thread_comment_context.get():
                # Email-thread comments have no standalone Content row; they're indexed only
                # through the thread's IndexEmailThreadJob (which inlines comment bodies),
                # matching how goal/document comments are handled.
                await comment.fetch_related("user", "email_thread")
                await enqueue_job(ContentIndexingJob.from_model(comment.user.organization_id, comment.email_thread))

    return _index_email_thread_comment


async def get_post(post_id: UUID, user: User = Depends(get_current_user)):
    async with transaction() as connection:
        post = await Post.get(id=post_id, organization_id=user.organization_id, using_db=connection).prefetch_related(
            "workspace__collaborators__user__avatar_file",
            "creator__avatar_file",
            "group",
            "comments__user__avatar_file",
            "comments__replies__user__avatar_file",
        )

    if post.sharing == Sharing.PRIVATE and not post.collaboration.can_be_accessed_by(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    post_context.set(post)
    return post


async def get_draft_post(post_id: UUID, current_user: User = Depends(get_current_user)):
    post = await (
        Post.filter(
            id=post_id,
            organization_id=current_user.organization_id,
        )
        .filter(PostFilters.drafts_visible_to(current_user.id))
        .first()
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    post_context.set(post)
    return post


document_context: ContextVar[Document | None] = ContextVar("document_context", default=None)


async def index_document(request: Request):
    yield
    if request.method.lower() in ["post", "put", "patch", "delete"]:
        if document := document_context.get():
            await enqueue_job(ContentIndexingJob.from_model(document.organization_id, document))


async def get_document(document_id: UUID, current_user: User = Depends(get_current_user)) -> Document:
    document = await Document.get(id=document_id, organization_id=current_user.organization_id).prefetch_related(
        "workspace__collaborators__user__avatar_file", "creator"
    )

    if document.collaboration.can_be_accessed_by(current_user):
        document_context.set(document)
        return document

    if document.organization_id == current_user.organization_id:
        raise RequestAccessError(global_id=str(document.global_id))

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


async def get_mailbox(current_user: User = Depends(get_current_user)) -> Mailbox:
    return Mailbox(user=current_user)


async def get_mailbox_entry_for_resource(
    mailbox_entry_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
) -> MailboxEntry | None:
    if not mailbox_entry_id:
        return None
    return await MailboxEntry.get_or_none(id=mailbox_entry_id, owner_id=current_user.id)


async def get_all_org_groups(current_user: User = Depends(get_current_user)) -> list[Group]:
    return (
        await Group.filter(Group.filters.by_organization(current_user.organization_id))
        .prefetch_related("members")
        .all()
    )


@dataclass
class UnclaimedAttachments:
    claim_id: UUID | None
    attachments: list[Attachment]

    @classmethod
    def empty(cls) -> "UnclaimedAttachments":
        return cls(claim_id=None, attachments=[])

    @classmethod
    async def find(cls, claim_id: UUID, user_id: UUID):
        attachments = await Attachment.filter(claim_id=claim_id, user_id=user_id).prefetch_related("file")
        return cls(claim_id, attachments)

    @classmethod
    async def resolve(cls, claim_id: UUID | None, user_id: UUID) -> "UnclaimedAttachments":
        if not claim_id:
            return cls.empty()
        return await cls.find(claim_id, user_id)

    async def claim(
        self, workspace: Workspace, comment: CommentMixin | None = None, using_db: BaseDBAsyncClient | None = None
    ):
        for attachment in self.attachments:
            if not attachment.workspace_id:
                attachment.workspace_id = workspace.id
            elif attachment.workspace_id != workspace.id:
                continue

            if comment:
                attachment.comment_gid = comment.global_id
            attachment.claim_id = None
            await attachment.save(using_db=using_db)

        if comment:
            await comment.cleanup_unreferenced_attachments(using_db=using_db)

    async def claim_for_comment(
        self,
        comment: CommentMixin,
        *,
        retained_attachment_ids: list[UUID] | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ):
        for attachment in self.attachments:
            attachment.comment_gid = comment.global_id
            attachment.claim_id = None
            await attachment.save(using_db=using_db)

        if retained_attachment_ids is not None:
            # Intent-based cleanup: caller passed the IDs its editor still references.
            # Avoids URL-substring matching, which mis-fires after ProseMirror round-trips.
            keep_ids = {a.id for a in self.attachments} | set(retained_attachment_ids)
            await (
                Attachment.filter(comment_gid=comment.global_id)
                .exclude(id__in=list(keep_ids))
                .using_db(using_db)
                .delete()
            )
        elif self.attachments:
            # Compose fallback: scan the freshly-saved content for which claimed
            # attachments are still referenced. Skip on no-op claims so text-only
            # comments don't trigger an unnecessary scan. This path saves content
            # straight from a composer that embeds every attachment as a link
            # (images as ![](url), files as [name](url)), so non-image files are
            # eligible for content-referenced cleanup here.
            await comment.cleanup_unreferenced_attachments(using_db=using_db, include_non_images=True)

    async def claim_without_workspace(self, using_db: BaseDBAsyncClient | None = None):
        """Claim attachments by clearing their claim_id without assigning to a workspace."""
        if not self.attachments:
            return

        for attachment in self.attachments:
            attachment.claim_id = None
            await attachment.save(using_db=using_db)


meeting_context: ContextVar[Meeting | None] = ContextVar("meeting_context", default=None)


async def index_meeting(request: Request):
    yield
    if request.method.lower() in ["post", "put", "patch", "delete"]:
        if meeting := meeting_context.get():
            await enqueue_job(ContentIndexingJob.from_model(meeting.organization_id, meeting))


async def get_meeting(meeting_id: UUID, current_user: User = Depends(get_current_user)):
    meeting = await Meeting.get(id=meeting_id).prefetch_related(
        "organization",
        "workspace__collaborators__user",
        "jobs__job",
        "recording",
        "collection",
    )

    if meeting.collaboration.can_be_accessed_by(current_user):
        meeting_context.set(meeting)
        return meeting

    if meeting.organization_id == current_user.organization_id:
        raise RequestAccessError(global_id=str(meeting.global_id))

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")


async def get_draft_for_channel(thread_id: UUID, user: User) -> EmailDraft | None:
    """Channel-handler counterpart to get_email_draft: returns None instead of raising."""
    thread = await EmailThread.get_or_none(id=thread_id, organization_id=user.organization_id).prefetch_related(
        "workspace__collaborators__user", "workspace__assignee", "messages__attachments__file", "creator"
    )
    if not thread or not thread.collaboration.can_be_accessed_by(user):
        return None
    return await thread.get_draft()


async def get_email_draft(email_thread_id: UUID, current_user: User = Depends(get_current_user)) -> EmailDraft:
    """Get an email draft record. Note that EmailDraft is always accessed through the thread."""
    thread = await EmailThread.get(id=email_thread_id, organization_id=current_user.organization_id).prefetch_related(
        "workspace__collaborators__user", "workspace__assignee", "messages__attachments__file", "creator"
    )

    if not thread.collaboration.can_be_accessed_by(current_user):
        raise RequestAccessError(global_id=str(thread.global_id))

    email_draft = await thread.get_draft()
    if not email_draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email draft not found")

    return email_draft


async def get_email_draft_for_deletion(
    email_thread_id: UUID, current_user: User = Depends(get_current_user)
) -> EmailDraft:
    """Lightweight draft fetch for deletion — skips loading all messages/attachments."""
    thread = await EmailThread.get(id=email_thread_id, organization_id=current_user.organization_id).prefetch_related(
        "workspace__collaborators__user", "creator"
    )

    if not thread.collaboration.can_be_accessed_by(current_user):
        raise RequestAccessError(global_id=str(thread.global_id))

    draft_message = await EmailMessage.filter(thread_id=thread.id, message_type=EmailMessageType.DRAFT).first()
    if not draft_message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email draft not found")

    draft_message.thread = thread
    return EmailDraft(message=draft_message)


#
# LLM completion streaming
#
#

CompletionStreamSubscriber = Callable[[dict[str, str]], Awaitable[None]]


class CompletionStream(Protocol):
    subscribers: list[CompletionStreamSubscriber]
    is_complete: bool
    _lock: asyncio.Lock

    def ensure_task(self) -> None: ...
    async def subscribe(self, subscriber: CompletionStreamSubscriber) -> None: ...


@dataclass
class CompletionStreamManager:
    _active_completions: dict[str, Any] = field(default_factory=dict, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def get_or_create_completion(
        self, id: str, completion_factory: Callable[[], CompletionStream]
    ) -> CompletionStream:
        async with self._lock:
            if id not in self._active_completions:
                completion = completion_factory()
                self._active_completions[id] = completion
            return self._active_completions[id]

    async def cleanup_completion(self, id: str):
        async with self._lock:
            if id in self._active_completions:
                del self._active_completions[id]


async def stream_with_subscribers(
    completion: CompletionStream, id: str, stream_manager: CompletionStreamManager
) -> AsyncGenerator[dict[str, str]]:
    completion.ensure_task()
    queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()

    async def subscriber(event: dict[str, str]):
        await queue.put(event)

    await completion.subscribe(subscriber)
    try:
        while True:
            event = await queue.get()
            yield event
            if event.get("event") == "end":
                break
    finally:
        async with completion._lock:
            if subscriber in completion.subscribers:
                completion.subscribers.remove(subscriber)
            if completion.is_complete and len(completion.subscribers) == 0:
                await stream_manager.cleanup_completion(id)


#
# Request helpers
#
#


async def get_helpers(
    connection: HTTPConnection,
    templates: Jinja2Templates = Depends(get_templates),
    authentication: Authentication = Depends(get_authentication),
):
    return Helpers(connection=connection, templates=templates, authentication=authentication)


@dataclass
class Flash:
    content: str
    level: str


@dataclass
class Helpers:
    connection: HTTPConnection
    templates: Jinja2Templates
    authentication: Authentication

    def __post_init__(self):
        self.set_template_variant()

    @property
    def request(self):
        if not isinstance(self.connection, Request):
            raise AttributeError("request property only available for Request connections, not WebSocket")
        return self.connection

    @property
    def session(self):
        return self.connection.session

    @property
    def timezone(self):
        # Cookie fallback covers unauthenticated connections and requests before
        # the zone is backfilled onto the user.
        current_user = self.authentication.current_user
        candidates = [
            current_user.time_zone if current_user else None,
            self.connection.cookies.get("timezone"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                return ZoneInfo(candidate)
            except (ZoneInfoNotFoundError, ValueError):
                continue
        return ZoneInfo(DEFAULT_TIMEZONE)

    def is_route_tagged(self, tag: str) -> bool:
        route = self.connection.scope.get("route")
        if not route:
            return False
        # FastAPI 0.136+ stopped flattening included routers into `app.routes`, so
        # `scope["route"]` is the original (unprefixed) APIRoute whose `.tags` omit
        # tags inherited from the router it was mounted under — e.g. the `/api`
        # router's `skip_onboarding`, or the per-feature `inbox`/`goals` tags used
        # for nav highlighting. Resolve the effective, merged tags instead.
        effective_tags = _effective_route_tags(self.connection.app).get(id(route))
        if effective_tags is not None:
            return tag in effective_tags
        return tag in {str(t) for t in (getattr(route, "tags", None) or [])}

    @property
    def is_xhr(self):
        return (
            self.connection.headers.get("hx-request") == "true"
            and not self.connection.headers.get("hx-boosted") == "true"
            and not self.connection.headers.get("hx-history-restore-request") == "true"
        )

    @property
    def is_targeted(self):
        return self.connection.headers.get("hx-target", None) is not None

    @property
    def is_sse(self):
        return self.connection.headers.get("accept") == SSE_ACCEPT_HEADER

    @property
    def csrf_token(self):
        token = self.session.get("csrf_token")
        return str(token) if token else None

    @property
    def csp_nonce(self) -> str:
        # Set by SecureHeadersMiddleware. May be absent in tests that bypass
        # the middleware stack — fall back to "" so templates render
        # `nonce=""` (which CSP treats as "no nonce") rather than the literal
        # string "None" from Jinja's default rendering of None.
        return getattr(self.connection.state, "csp_nonce", "") or ""

    @property
    def application_layout(self):
        if self.is_xhr or self.is_targeted or self.is_sse:
            return "layouts/content.html.jinja"
        return "layouts/application.html.jinja"

    @property
    def public_layout(self):
        if self.is_xhr or self.is_targeted or self.is_sse:
            return "layouts/content.html.jinja"
        return "layouts/public.html.jinja"

    @property
    def is_mobile(self):
        user_agent = self.connection.headers.get("user-agent", "").lower()
        mobile_indicators = ["mobile", "android", "iphone", "ipad", "tablet", "opera mini", "blackberry"]
        return any(indicator in user_agent for indicator in mobile_indicators)

    @property
    def is_ios(self):
        user_agent = self.connection.headers.get("user-agent", "").lower()
        ios_indicators = ["iphone", "ipad", "ipod"]
        return any(indicator in user_agent for indicator in ios_indicators)

    @property
    def is_embedded_browser(self):
        user_agent = self.connection.headers.get("user-agent", "")
        # Google OAuth is blocked in embedded WebViews (LinkedIn, Facebook, etc.)
        embedded_indicators = ["; wv)", "LinkedInApp", "FBAN", "FBAV", "Instagram", "BytedanceWebview", "Line/"]
        return any(indicator in user_agent for indicator in embedded_indicators)

    async def form(self):
        return await self.request.form()

    def url_for(self, name: str, /, **path_params: Any) -> URL:
        return self.connection.url_for(name, **path_params)

    def flash(self, message: str, level: FlashLevel = FlashLevel.SUCCESS):
        flashes: list[dict] = self.session.get("flashes", [])
        flash_dict = {"content": message, "level": level.value}
        flashes.append(flash_dict)
        self.session["flashes"] = flashes

    def get_flashed_messages(self) -> list[Flash]:
        flashes_dicts: list[dict] = self.session.get("flashes", [])

        # Avoid modifying the session if there are no flashes
        if len(flashes_dicts) > 0:
            self.session["flashes"] = []
        return [Flash(**flash_dict) for flash_dict in flashes_dicts]

    def remember_location(self, location: str | URL | None = None):
        if location:
            location = build_safe_redirect_url(str(location))

        target = str(location or "") or self.connection.url.path
        # API routes return JSON and must never become a post-login redirect target (#8050).
        if target.startswith(f"{API_PREFIX}/"):
            return

        self.session["redirect_to"] = target

    def set_template_variant(self):
        variant = "mobile" if self.is_mobile else None
        template_variant.set(variant)

    def rendering_context(self, *, consume_flashes: bool = True):
        return {
            "request": self.connection,
            "application_layout": self.application_layout,
            "public_layout": self.public_layout,
            "authentication": self.authentication,
            "current_user": self.authentication.current_user,
            # Reading the flashes clears them, so only a template that actually displays
            # them may render with consume_flashes=True. The SPA shell hands them to the
            # client through /api/users/me instead and opts out.
            "flash_messages": self.get_flashed_messages() if consume_flashes else [],
            "settings": settings,
            "referrer": self.referrer,
            "csrf_token": self.csrf_token,
            "csp_nonce": self.csp_nonce,
            "session_created_at": self.session.get("created_at", ""),
            "timezone": self.timezone,
            "is_route_tagged": self.is_route_tagged,
            "is_xhr": self.is_xhr,
            "is_mobile": self.is_mobile,
            "is_ios": self.is_ios,
            "is_embedded_browser": self.is_embedded_browser,
        }

    def render(self, template: str, *, consume_flashes: bool = True, **context):
        context = {**self.rendering_context(consume_flashes=consume_flashes), **context}
        return self.templates.TemplateResponse(self.request, template, context)

    def render_to_string(self, template: str, **context) -> str:
        context = {**self.rendering_context(), **context}
        return self.templates.env.get_template(template).render(context)

    def no_content(self, redirect: str | None = None):
        headers = {"HX-Redirect": redirect} if redirect else None
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)

    def redirect_to(self, to: str | URL, status_code: int = status.HTTP_303_SEE_OTHER):
        return RedirectResponse(to or "/", status_code=status_code)

    async def redirect_back_or(self, to: str | URL = "", status_code: int = status.HTTP_303_SEE_OTHER):
        url = self.session.pop("redirect_to", None)
        if not url:
            url = await self.redirect_from_request()

        return RedirectResponse(url or to or "/", status_code=status_code)

    async def redirect_from_request(self, query_param: str | None = None) -> str | None:
        redirect_to = self.connection.query_params.get(query_param or "redirect_to", None)
        if not redirect_to:
            form_data = await self.form()
            redirect_to = str(form_data.get(query_param or "redirect_to", None))

        if not redirect_to:
            return None

        return build_safe_redirect_url(redirect_to)

    @property
    def referrer(self) -> str | None:
        header = self.connection.headers.get("referer")
        if not header:
            return None
        if header == self.connection.url:
            return None

        return build_safe_redirect_url(header)

    def stream_sse(self, event_generator: AsyncGenerator):
        return EventSourceTimeoutResponse(content=event_generator)


class EventSourceTimeoutResponse(EventSourceResponse):
    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        try:
            async with asyncio.timeout(settings.sse_connection_timeout):
                await super().__call__(scope, receive, send)
        except TimeoutError:
            return


#
# Channels
#
#


class EventMessage(ChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.EVENT
    resource: ChannelEventResource
    action: ChannelEventAction
    data: dict[str, Any] = {}


@dataclass(kw_only=True)
class Channel(BaseChannel):
    helpers: Helpers
    authentication: Authentication

    @property
    def current_user(self):
        return self.authentication.current_user

    async def send_event(self, resource: ChannelEventResource, action: ChannelEventAction, **data: Any) -> None:
        await self.session.send(
            EventMessage(
                topic_stream=self.topic.stream,
                topic_params=self.topic.params,
                resource=resource,
                action=action,
                data=data,
            )
        )


def handle_stream(stream: str):
    def decorator(func: BroadcastHandler) -> BroadcastHandler:
        async def wrapper(channel: BaseChannel, **data) -> None:
            helpers = channel.session.context.get("helpers")
            if not isinstance(helpers, Helpers):
                raise ValueError("helpers context must be an instance of the Helpers class")
            authentication = channel.session.context.get("authentication")
            if not isinstance(authentication, Authentication):
                raise ValueError("authentication context must be an instance of the Authentication class")

            channel = Channel(
                channel.topic, channel.session, channel.params, helpers=helpers, authentication=authentication
            )
            await func(channel, **data)

        channels.broadcast_handlers.add(stream, wrapper)
        return func

    return decorator
