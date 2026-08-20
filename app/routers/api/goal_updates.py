from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from tortoise import BaseDBAsyncClient

from app.helpers.markdown import render_markdown
from app.jobs.content import ContentIndexingJob
from app.jobs.goals import create_goal_update_request
from app.jobs.notifications import Notifier
from app.models.accounts import Group, OrganizationUpdatesConfiguration, User
from app.models.collaboration.workspace import Attachment, Visit
from app.models.workspaces.goals import Goal, GoalUpdate
from app.routers.api.schemas import UserResponse
from app.routers.api.serializers import user_response
from app.routers.dependencies import get_current_user, get_goal
from config.enums import EventAction, GoalStatus
from infra.db import transaction
from infra.jobs import enqueue_job

#
# Dependencies
#
#

goal_update_context: ContextVar[Goal | None] = ContextVar("goal_update_context", default=None)


async def get_goal_with_indexing(goal: Goal = Depends(get_goal)) -> Goal:
    goal_update_context.set(goal)
    return goal


async def index_goal_on_update(request: Request):
    yield
    if request.method.lower() in ["post", "put", "patch", "delete"]:
        if goal := goal_update_context.get():
            await enqueue_job(ContentIndexingJob.from_model(goal.organization_id, goal))


async def can_user_update_goal(user: User, goal: Goal) -> bool:
    if goal.owner_id == user.id:
        return True
    if goal.group_id:
        group_ids = await Group.filter(Group.filters.by_member(user.id)).values_list("id", flat=True)
        return goal.group_id in group_ids
    return False


async def get_goal_with_authentication(
    goal: Goal = Depends(get_goal_with_indexing),
    current_user: User = Depends(get_current_user),
) -> Goal:
    if not await can_user_update_goal(current_user, goal):
        raise HTTPException(status_code=404, detail="Goal update not found")
    return goal


router = APIRouter(dependencies=[Depends(index_goal_on_update, scope="function")], tags=["goal updates"])


#
# Params
#
#


@dataclass
class GoalUpdateParams:
    status: GoalStatus
    question_text: str
    answer_text: str | None
    progress: float | None

    def apply_to(self, goal_update: GoalUpdate, goal: Goal, *, creator_id: UUID):
        goal_update.creator_id = creator_id
        goal_update.status = self.status
        goal_update.answer_text = self.answer_text
        goal_update.question_text = self.question_text
        goal_update.progress = self.progress

        goal.status = self.status
        # Write unconditionally so untracked (null) propagates to the goal, not just tracked values.
        goal.progress = self.progress


#
# Response models
#
#


class GoalUpdateResponse(BaseModel):
    id: str
    status: str
    progress: float | None
    question_text: str
    answer_text: str | None
    answer_html: str | None
    is_completed: bool
    created_at: datetime
    creator: UserResponse | None


class LatestUpdateResponse(BaseModel):
    latest_update: GoalUpdateResponse | None
    question_text: str
    group_members: list[UserResponse]


class PendingUpdateResponse(BaseModel):
    id: str | None = None
    question_text: str
    status: str | None = None
    progress: float | None = None
    answer_text: str | None = None


#
# Request models
#
#


class SubmitUpdateRequest(BaseModel):
    status: GoalStatus
    question_text: str = Field(min_length=1)
    answer_text: str | None = None
    progress: float | None = Field(None, ge=0, le=1)
    is_draft: bool = False
    update_id: UUID | None = None

    def to_params(self) -> GoalUpdateParams:
        return GoalUpdateParams(
            status=self.status,
            question_text=self.question_text,
            answer_text=self.answer_text or None,
            progress=self.progress,
        )


class RequestUpdateRequest(BaseModel):
    question_text: str = Field(min_length=1)


#
# Mutations
#
#


async def record_goal_update_event(
    goal: Goal,
    goal_update: GoalUpdate,
    *,
    current_user: User,
    is_goal_completed: bool,
    using_db: BaseDBAsyncClient | None = None,
):
    notifier = Notifier(goal, current_user)
    async with notifier.record_and_notify(
        action=EventAction.GOAL_UPDATE_POSTED, recordable=goal_update, using_db=using_db
    ) as recording:
        recording.event.details["question_text"] = goal_update.question_text
        recording.event.details["is_completed"] = is_goal_completed
        await goal_update.save(using_db=recording.using_db)
        if goal_update.answer_text:
            await goal.workspace.fetch_related("collaborators__user", using_db=recording.using_db)
            await recording.resolve_mentions(goal_update.answer_text, recordable=goal_update)
        await goal.save(update_fields=goal.changes.keys(), using_db=recording.using_db)
        await Visit.record(current_user.id, goal.workspace_id, recording.event.id, using_db=recording.using_db)

        # Claim attachments inside the recording transaction so a rollback can't leave
        # them claimed with no GoalUpdate referencing them.
        await Attachment.claim_referenced_in_content(
            goal.workspace_id, current_user.id, goal_update.answer_text or "", using_db=recording.using_db
        )

    await goal.broadcast_update()


async def submit_goal_update(
    goal: Goal,
    params: GoalUpdateParams,
    current_user: User,
    *,
    is_draft: bool = False,
    update_id: UUID | None = None,
) -> GoalUpdate | None:
    if is_draft:
        # Suppress the index_goal_on_update teardown reindex for every draft outcome,
        # including the no-op below.
        goal_update_context.set(None)

        if update_id is not None:
            # If it's no longer pending, a completing submit already resolved it — no-op
            # rather than resurrect it.
            row = await GoalUpdate.filter(GoalUpdate.filters.pending_for_goal(goal.id), id=update_id).first()
            if row is None:
                return None

            params.apply_to(row, goal, creator_id=current_user.id)
            # Save and claim share a transaction so a claim failure can't leave a persisted
            # draft pointing at attachments that are still eligible for cleanup.
            async with transaction() as connection:
                # Scope to changed fields so a stale draft can never overwrite completed_at/
                # closed_at (apply_to never assigns them), reverting completion.
                if row.changes:
                    await row.save(update_fields=list(row.changes.keys()), using_db=connection)
                # Referenced attachments get claimed so a long-lived draft's files survive the
                # unclaimed grace period; anything the draft doesn't reference keeps its claim_id
                # and stays sweepable, so an abandoned draft's uploads aren't retained forever.
                await Attachment.claim_referenced_in_content(
                    goal.workspace_id, current_user.id, row.answer_text or "", using_db=connection
                )
            return row

        goal_update = await GoalUpdate.pending_or_new_for_goal(goal)
        params.apply_to(goal_update, goal, creator_id=current_user.id)
        async with transaction() as connection:
            await goal_update.save(using_db=connection)
            await Attachment.claim_referenced_in_content(
                goal.workspace_id, current_user.id, goal_update.answer_text or "", using_db=connection
            )
        return goal_update

    goal_update = await GoalUpdate.pending_or_new_for_goal(goal)
    params.apply_to(goal_update, goal, creator_id=current_user.id)
    goal_update.is_completed = True
    await record_goal_update_event(
        goal,
        goal_update,
        current_user=current_user,
        is_goal_completed=False,
    )
    return goal_update


async def complete_goal_with_update(
    goal: Goal,
    params: GoalUpdateParams,
    current_user: User,
) -> GoalUpdate:
    marking_complete = not goal.is_completed

    goal_update = GoalUpdate(goal=goal)
    params.apply_to(goal_update, goal, creator_id=current_user.id)
    goal_update.is_completed = True

    async with transaction() as connection:
        if marking_complete:
            async with goal.workspace.record(
                EventAction.GOAL_COMPLETED, creator_id=current_user.id, using_db=connection
            ):
                await goal.complete(using_db=connection)

        await record_goal_update_event(
            goal,
            goal_update,
            current_user=current_user,
            is_goal_completed=True,
            using_db=connection,
        )

    return goal_update


async def request_goal_update(
    goal: Goal,
    question_text: str,
    current_user: User,
) -> GoalUpdate:
    question_text = question_text.strip()

    if not goal.owner_id:
        raise HTTPException(status_code=422, detail="This goal has no owner to request an update from")

    return await create_goal_update_request(
        goal,
        question_text,
        goal.owner_id,
        requested_by=current_user,
    )


#
# Helpers
#
#


def _goal_update_response(goal_update: GoalUpdate) -> GoalUpdateResponse:
    return GoalUpdateResponse(
        id=str(goal_update.id),
        status=goal_update.status.value,
        progress=goal_update.progress,
        question_text=goal_update.question_text,
        answer_text=goal_update.answer_text,
        answer_html=str(render_markdown(goal_update.answer_text)) if goal_update.answer_text else None,
        is_completed=goal_update.is_completed,
        created_at=goal_update.created_at,
        creator=user_response(goal_update.creator),
    )


#
# Endpoints
#
#


@router.get("/goals/{goal_id}/updates/latest", response_model=LatestUpdateResponse)
async def api_goal_updates_latest(
    goal: Goal = Depends(get_goal),
    current_user: User = Depends(get_current_user),
):
    latest_update = (
        await GoalUpdate.filter(GoalUpdate.filters.completed_for_goal(goal.id))
        .order_by("-created_at")
        .prefetch_related("creator__avatar_file")
        .first()
    )

    config = await OrganizationUpdatesConfiguration.get_or_none(organization_id=current_user.organization_id)
    question_text = config.goal_update_question if config else "How's it going?"

    group_members: list[UserResponse] = []
    if goal.group_id and not goal.owner_id:
        await goal.fetch_related("group__members__user__avatar_file")
        if goal.group:
            group_members = [r for member in goal.group.members if (r := user_response(member.user))]

    return LatestUpdateResponse(
        latest_update=_goal_update_response(latest_update) if latest_update else None,
        question_text=question_text,
        group_members=group_members,
    )


@router.get(
    "/goals/{goal_id}/updates/pending",
    response_model=PendingUpdateResponse,
    responses={204: {"description": "No pending update"}},
)
async def api_goal_updates_pending(
    goal: Goal = Depends(get_goal),
    current_user: User = Depends(get_current_user),
):
    if goal.owner_id != current_user.id:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    config = await OrganizationUpdatesConfiguration.get_or_none(organization_id=current_user.organization_id)
    default_question = config.goal_update_question if config else "How's it going?"

    pending = await GoalUpdate.pending_for_goal(goal.id)
    if not pending:
        return PendingUpdateResponse(question_text=default_question)

    return PendingUpdateResponse(
        id=str(pending.id),
        question_text=pending.question_text,
        status=pending.status.value,
        progress=pending.progress,
        answer_text=pending.answer_text,
    )


@router.post(
    "/goals/{goal_id}/updates",
    response_model=GoalUpdateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={204: {"description": "Draft no-op (request already resolved)"}},
)
async def api_goal_updates_submit(
    body: SubmitUpdateRequest,
    response: Response,
    goal: Goal = Depends(get_goal_with_authentication),
    current_user: User = Depends(get_current_user),
):
    goal_update = await submit_goal_update(
        goal, body.to_params(), current_user, is_draft=body.is_draft, update_id=body.update_id
    )
    if goal_update is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if body.is_draft:
        # A draft updates the existing pending GoalUpdate rather than creating one.
        response.status_code = status.HTTP_200_OK
    goal_update.creator = current_user
    return _goal_update_response(goal_update)


@router.post(
    "/goals/{goal_id}/updates/complete", response_model=GoalUpdateResponse, status_code=status.HTTP_201_CREATED
)
async def api_goal_updates_complete(
    body: SubmitUpdateRequest,
    goal: Goal = Depends(get_goal_with_authentication),
    current_user: User = Depends(get_current_user),
):
    goal_update = await complete_goal_with_update(goal, body.to_params(), current_user)
    goal_update.creator = current_user
    return _goal_update_response(goal_update)


@router.post(
    "/goals/{goal_id}/updates/request", response_model=GoalUpdateResponse, status_code=status.HTTP_201_CREATED
)
async def api_goal_updates_request(
    body: RequestUpdateRequest,
    goal: Goal = Depends(get_goal_with_indexing),
    current_user: User = Depends(get_current_user),
):
    goal_update = await request_goal_update(goal, body.question_text, current_user)
    await goal_update.fetch_related("creator__avatar_file")
    return _goal_update_response(goal_update)
