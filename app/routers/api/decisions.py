from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from tortoise.exceptions import IntegrityError

from app.jobs.content import IndexDecisionJob
from app.jobs.notifications import Notifier
from app.models.accounts import User
from app.models.collaboration.workspace import CommentMixin, Decision, Workspace
from app.models.workspaces.chat import ChatMessage
from app.models.workspaces.documents import DocumentComment
from app.models.workspaces.email.thread import EmailThreadComment
from app.models.workspaces.goals import GoalComment
from app.models.workspaces.posts import PostComment
from app.routers.api.schemas import DecisionCreateRequest, DecisionListResponse, DecisionResponse
from app.routers.api.serializers import user_response
from app.routers.dependencies import Channel, get_current_user, get_workspace, handle_stream, index_workspace_resource
from config.enums import ChannelEventAction, ChannelEventResource, EventAction
from infra.db import GlobalID, SoftDeleteableMixin
from infra.jobs import enqueue_job

# index_workspace_resource re-indexes the parent resource after any mutating
# request (it reads the workspace set by get_workspace), keeping the parent's
# decision metadata current without a hand-rolled enqueue in each handler.
router = APIRouter(tags=["decisions"], dependencies=[Depends(index_workspace_resource, scope="function")])

# A deliberate allowlist, not isinstance(CommentMixin): PostDraftComment would
# pass the structural check, but draft-review comments are visible to a
# narrower audience than workspace access, so anchoring one would leak its
# content. Future comment types must weigh the same question before opting in.
ANCHORABLE_COMMENT_MODELS = (EmailThreadComment, PostComment, GoalComment, DocumentComment, ChatMessage)


#
# Helpers
#


def _decision_response(decision: Decision, comment: CommentMixin, decided_by: User | None) -> DecisionResponse:
    is_tombstone = isinstance(comment, SoftDeleteableMixin) and comment.is_deleted
    return DecisionResponse(
        id=str(decision.id),
        comment_gid=str(decision.comment_gid),
        comment_preview=None if is_tombstone else comment.content,
        decided_by=user_response(decided_by),
        decided_at=decision.decided_at,
    )


async def _get_workspace_comment(workspace: Workspace, comment_gid: str) -> CommentMixin:
    not_found = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    # KeyError covers foreign app names and unknown record types (the registry
    # lookup), ValueError/IndexError cover malformed gids and non-UUID ids.
    try:
        comment = await GlobalID.parse(comment_gid).get_or_none()
    except (KeyError, ValueError, IndexError):
        raise not_found from None
    if comment is None or not isinstance(comment, ANCHORABLE_COMMENT_MODELS):
        raise not_found

    # Type-agnostic ownership check mirroring CommentMixin.comment_topic: every
    # anchorable comment's parent param points at the workspace's resource (the
    # email thread, post, goal, document, or chat it belongs to).
    param = type(comment).comment_topic_param
    if getattr(comment, param) != workspace.resource_id:
        raise not_found

    return comment


async def _resolve_comments(gids: list[GlobalID]) -> dict[GlobalID, CommentMixin]:
    # Batch: one query per comment table. Unscoped, because the default
    # NonDeletedManager on soft-deletable comment models would hide a
    # soft-deleted anchor — the list must render it as a tombstone, not
    # silently drop the decision.
    comments: dict[GlobalID, CommentMixin] = {}
    for model in ANCHORABLE_COMMENT_MODELS:
        ids = [gid.record_id for gid in gids if gid.record_type == model.record_type]
        if not ids:
            continue
        for comment in await model.unscoped.filter(id__in=ids):
            comments[comment.global_id] = comment
    return comments


#
# Endpoints
#
# get_workspace's can_be_accessed_by gate guards every verb. Recording is
# reaction-grade on top of it — anyone who can see the workspace may mark a
# decision. Clearing is narrower: only the decider or an org admin may undecide
# (enforced in the delete handler), so one member can't undo another's decision.
#


@router.post(
    "/workspaces/{workspace_id}/decisions",
    response_model=DecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_decisions_create(
    body: DecisionCreateRequest,
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    comment = await _get_workspace_comment(workspace, body.comment_gid)

    # The recordable is the workspace resource (not the Decision): reach follows
    # the resource's comment contours, and the activity feed can render it.
    notifier = Notifier(workspace.resource, current_user)
    try:
        async with notifier.record_and_notify(EventAction.DECIDED) as recording:
            decision = await Decision.create(
                workspace_id=workspace.id,
                comment_gid=comment.global_id,
                decided_by_id=current_user.id,
                decided_at=datetime.now(UTC),
                using_db=recording.using_db,
            )
            # The recordable is the resource, so its change-tracking captures
            # nothing about the comment; stash the decided comment's body in
            # details for the mailer ([old, new] shape, like commented.jinja).
            recording.event.details["content"] = [None, comment.content]
            recording.event.details["comment_gid"] = comment.global_id.to_param
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Comment already has a decision") from None

    await Decision.broadcast_change(workspace.id, actor_id=current_user.id)

    # Index the new decision row; the parent re-index is handled by the
    # index_workspace_resource router dependency.
    await enqueue_job(IndexDecisionJob.from_model(workspace.organization_id, decision))

    return _decision_response(decision, comment, decided_by=current_user)


@router.get("/workspaces/{workspace_id}/decisions", response_model=DecisionListResponse)
async def api_decisions_index(workspace: Workspace = Depends(get_workspace)):
    decisions = await Decision.filter(workspace_id=workspace.id).prefetch_related("decided_by")
    comments = await _resolve_comments([decision.comment_gid for decision in decisions])

    responses = []
    for decision in decisions:
        comment = comments.get(decision.comment_gid)
        if comment is None:
            # Orphaned anchor the cleanup hasn't swept yet — skip the row rather
            # than render a broken marker (or 500).
            continue
        responses.append(_decision_response(decision, comment, decided_by=decision.decided_by))

    return DecisionListResponse(
        decisions=responses,
    )


@router.delete("/workspaces/{workspace_id}/decisions/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_decisions_delete(
    decision_id: UUID,
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    decision = await Decision.get_or_none(id=decision_id, workspace_id=workspace.id)
    if not decision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")

    # Only the decider or an org admin may undecide — a member can't clear
    # someone else's decision. 403 (not 404): the requester has workspace access
    # and can already see the decision, so there's nothing to hide.
    if not decision.clearable_by(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the decider or an admin can undecide")

    # Clearing is silent by design (team decision 2026-06-09): no event, no
    # notification — but open tabs still get the channel signal to refetch.
    await decision.delete()
    await Decision.broadcast_change(workspace.id, actor_id=current_user.id)

    # Re-index the now-deleted decision (the job resolves no Decision and drops its
    # orphaned Content row). The parent re-index is handled by the
    # index_workspace_resource router dependency.
    await enqueue_job(IndexDecisionJob.from_model(workspace.organization_id, decision))

    return Response(status_code=status.HTTP_204_NO_CONTENT)


#
# Channel handler
#


@handle_stream("workspace_events")
async def handle_decisions_changed(channel: Channel, **data):
    # workspace_events carries both generic {event_id} broadcasts (handled in
    # workspace_events.py) and this action-tagged signal — dispatch on action.
    if data.get("action") != ChannelEventAction.DECISIONS_CHANGED or not channel.current_user:
        return

    await channel.send_event(
        resource=ChannelEventResource.DECISION,
        action=ChannelEventAction.DECISIONS_CHANGED,
        actor_id=data.get("actor_id"),
    )
