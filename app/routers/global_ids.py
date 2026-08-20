from collections.abc import Awaitable, Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from starlette.datastructures import URL

from app.models.accounts import User
from app.models.workspaces.chat import Chat
from app.models.workspaces.documents import Document, DocumentComment
from app.models.workspaces.email.thread import EmailThread, EmailThreadComment
from app.models.workspaces.goals import Goal, GoalComment
from app.models.workspaces.meetings import Meeting
from app.models.workspaces.posts import Post, PostComment
from app.routers.dependencies import Helpers, get_helpers
from infra.db import GlobalID, RecordModel

#
# Helpers
#
#


def _get_goal_list_url(helpers: Helpers, goal: Goal):
    if goal.is_closed:
        return helpers.url_for("goals_index").include_query_params(is_closed="true")
    elif goal.is_completed:
        return helpers.url_for("goals_index").include_query_params(is_completed="true")
    elif goal.planning_list_name:
        return helpers.url_for("goals_index").include_query_params(planning_list_name=goal.planning_list_name)
    else:
        return helpers.url_for("goals_index")


# Resolvers narrow `record` to their concrete model, so the param types are erased here
# (`...`); the registry guarantees each resolver only ever receives its mapped type.
WorkspaceUrlResolver = Callable[..., Awaitable[URL | str | None]]


async def _resolve_meeting(record: Meeting, global_id: GlobalID, helpers: Helpers) -> URL | str | None:
    url = helpers.url_for("meetings_show", meeting_id=record.id)
    if global_id.fragment:
        return f"{url}#{global_id.fragment}"
    return url


async def _resolve_goal(record: Goal, global_id: GlobalID, helpers: Helpers) -> URL | str | None:
    url = _get_goal_list_url(helpers, record)
    return f"{url}#goal-{record.id}"


async def _resolve_goal_comment(record: GoalComment, global_id: GlobalID, helpers: Helpers) -> URL | str | None:
    await record.fetch_related("goal")
    url = _get_goal_list_url(helpers, record.goal)
    return f"{url}#comment-{record.id}"


async def _resolve_post(record: Post, global_id: GlobalID, helpers: Helpers) -> URL | str | None:
    return helpers.url_for("posts_show", post_id=record.id)


async def _resolve_post_comment(record: PostComment, global_id: GlobalID, helpers: Helpers) -> URL | str | None:
    url = helpers.url_for("posts_show", post_id=record.post_id)
    return f"{url}#comment-{record.id}"


async def _resolve_document_comment(
    record: DocumentComment, global_id: GlobalID, helpers: Helpers
) -> URL | str | None:
    url = helpers.url_for("documents_edit", document_id=record.document_id)
    return f"{url}#comment-{record.id}"


async def _resolve_user(record: User, global_id: GlobalID, helpers: Helpers) -> URL | str | None:
    return f"{helpers.url_for('organization_users_index')}#user-{record.id}"


async def _resolve_email_thread_comment(
    record: EmailThreadComment, global_id: GlobalID, helpers: Helpers
) -> URL | str | None:
    await record.fetch_related("email_thread")
    thread = record.email_thread
    url = await get_workspace_url(thread, thread.global_id, helpers)
    # The email-thread comment island honors `#comment-<id>` deep links, so carry the
    # fragment onto the delegated resource URL instead of landing at the thread top.
    return f"{url}#comment-{record.id}"


async def _resolve_document(record: Document, global_id: GlobalID, helpers: Helpers) -> URL | str | None:
    return helpers.url_for("documents_show", document_id=record.id)


async def _resolve_email_thread(record: EmailThread, global_id: GlobalID, helpers: Helpers) -> URL | str | None:
    return helpers.url_for("email_threads_show", email_thread_id=record.id)


async def _resolve_chat(record: Chat, global_id: GlobalID, helpers: Helpers) -> URL | str | None:
    return helpers.url_for("chats_show", chat_id=record.id)


# The registry's keys are the canonical set of linkable record types. A test pins
# app.helpers.url.LINKABLE_CITATION_RECORD_TYPES (which helpers can't import from here)
# equal to these keys' names, so the two can't drift.
GID_URL_REGISTRY: dict[type[RecordModel], WorkspaceUrlResolver] = {
    Meeting: _resolve_meeting,
    Goal: _resolve_goal,
    GoalComment: _resolve_goal_comment,
    Post: _resolve_post,
    PostComment: _resolve_post_comment,
    DocumentComment: _resolve_document_comment,
    User: _resolve_user,
    EmailThreadComment: _resolve_email_thread_comment,
    Document: _resolve_document,
    EmailThread: _resolve_email_thread,
    Chat: _resolve_chat,
}


async def get_workspace_url(record: RecordModel, global_id: GlobalID, helpers: Helpers) -> URL | str | None:
    resolver = GID_URL_REGISTRY.get(type(record))
    if resolver is None:
        return None
    return await resolver(record, global_id, helpers)


#
# Routes
#
#

router = APIRouter()


@router.get("/gid/{gid}")
async def gid_redirect(request: Request, gid: str = Path(...), helpers: Helpers = Depends(get_helpers)):
    instance = GlobalID.from_param(gid)
    record = await instance.get()

    route = await get_workspace_url(record, instance, helpers)
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Redirect route not found")

    if request.query_params:
        parsed = urlparse(str(route))
        combined_query = urlencode(parse_qsl(parsed.query) + list(request.query_params.items()))
        route = urlunparse(parsed._replace(query=combined_query))

    return helpers.redirect_to(route)
