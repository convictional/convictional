from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from tortoise import BaseDBAsyncClient

from app.helpers.strings import titleize
from app.helpers.users import user_avatar_url
from app.jobs.content import ContentIndexingJob
from app.jobs.mailers import UserInvitedEmailJob
from app.jobs.notifications import Notifier
from app.models.accounts import Invite, User
from app.models.collaboration.live import Presence, workspace_scope_key
from app.models.collaboration.workspace import (
    Collaborator,
    CollaboratorViewState,
    ViewStateResolver,
    Workspace,
)
from app.presenters.collaborator import CollaboratorPresenter, CollaboratorsPresenter
from app.routers.api.schemas import (
    CollaboratorViewStateResponse,
    UserResponse,
    WorkspaceAccessRequest,
    WorkspaceAccessRequestState,
    WorkspaceAccessRequestSubmit,
    WorkspaceAccessRequestSubmitResponse,
    WorkspaceCollaboratorAddRequest,
    WorkspaceCollaboratorInviteRequest,
    WorkspaceCollaboratorResponse,
    WorkspaceCollaboratorsResponse,
    WorkspaceCollaboratorTypeaheadResponse,
    WorkspaceCollaboratorTypeaheadUser,
    WorkspaceViewerResponse,
)
from app.routers.dependencies import (
    Channel,
    Helpers,
    get_current_user,
    get_helpers,
    get_workspace,
    handle_stream,
    index_workspace_resource,
)
from config.enums import ChannelEventAction, ChannelEventResource, CollaboratorStatus, EventAction
from infra.db import transaction
from infra.jobs import enqueue_job

router = APIRouter(
    dependencies=[Depends(index_workspace_resource, scope="function")], tags=["workspace collaborators"]
)


#
# Collaborator helpers
#


async def get_pending_collaborator(collaborator_id: UUID):
    return await Collaborator.unscoped.get(id=collaborator_id, status=CollaboratorStatus.PENDING).prefetch_related(
        "user"
    )


async def add_collaborator(
    user: User, workspace: Workspace, current_user: User, reason: str, using_db: BaseDBAsyncClient | None = None
):
    async with transaction(using_db=using_db) as connection:
        _, was_added = await workspace.resource.collaboration.add(
            user_to_add=user, added_by_user=current_user, using_db=connection
        )

        if was_added:
            notifier = Notifier(workspace.resource, current_user=current_user, recipient=user)
            async with notifier.record_and_notify(EventAction.ADDED_COLLABORATOR, using_db=connection) as recording:
                recording.event.details.update({"collaborator": user.field_values, "reason": reason})

        await enqueue_job(
            ContentIndexingJob.from_model(workspace.organization_id, workspace.resource), using_db=connection
        )


async def remove_collaborator(workspace: Workspace, user: User) -> bool:
    async with transaction() as connection:
        collaborator, was_removed = await workspace.resource.collaboration.remove(user, using_db=connection)

        if was_removed:
            async with workspace.record(
                EventAction.REMOVED_COLLABORATOR, recordable=collaborator, using_db=connection
            ) as recording:
                recording.event.details.update({"collaborator": user.field_values})

    await enqueue_job(ContentIndexingJob.from_model(workspace.organization_id, workspace.resource))
    return was_removed


async def invite_and_add_collaborator(workspace: Workspace, current_user: User, email: str, reason: str) -> Invite:
    async with transaction() as connection:
        invite = Invite(inviter=current_user, email=email, using_db=connection)
        await invite.process()

        if not invite.success or not invite.invited:
            return invite

        await invite.invited.save(using_db=connection)
        if not invite.is_existing_user:
            # Invitation email only; the "new user" team notification fires on the invitee's first login.
            await enqueue_job(UserInvitedEmailJob(user_id=invite.invited.id, note=reason), using_db=connection)

        await invite.invited.fetch_related("oauth_tokens")
        await add_collaborator(invite.invited, workspace, current_user, reason, using_db=connection)

    return invite


def _user_response(user: User) -> UserResponse:
    return UserResponse(id=str(user.id), display_name=user.display_name, picture=user_avatar_url(user))


def _view_state_response(view_state: CollaboratorViewState) -> CollaboratorViewStateResponse:
    return CollaboratorViewStateResponse(
        viewed=view_state.viewed,
        last_viewed_at=view_state.last_viewed_at,
        last_viewed_event_id=view_state.last_viewed_event_id,
    )


def _collaborator_response(
    presenter: CollaboratorPresenter, status: str, view_state: CollaboratorViewState
) -> WorkspaceCollaboratorResponse:
    return WorkspaceCollaboratorResponse(
        id=str(presenter.model.id),
        user=_user_response(presenter.model.user),
        is_removable=presenter.is_removable,
        status=status,
        view_state=_view_state_response(view_state),
    )


async def _build_response(workspace: Workspace, current_user: User) -> WorkspaceCollaboratorsResponse:
    presenter = await CollaboratorsPresenter.create(workspace)

    present_user_ids = await Presence(scope_key=workspace_scope_key(workspace.id)).get_active_user_ids()

    # Seen-by spans everyone who has visited — collaborators, pending, and org-member viewers alike.
    # Deriving it from the collaborator roster alone dropped non-collaborator viewers (a regression vs
    # the old goal timeline). Resolved through ViewStateResolver, the single read path from Visit rows;
    # a roster member who never visited falls back to the unviewed default.
    visitor_states = await ViewStateResolver.all_visitors_for_workspace(workspace.id)

    def view_state_for(user_id: UUID) -> CollaboratorViewState:
        return visitor_states.get(user_id) or CollaboratorViewState.unviewed()

    approved_ids = {c.model.user_id for c in presenter}
    # Viewers = visitors who aren't approved collaborators (else they'd be missing from seen-by) and
    # aren't the requester (whose state rides current_user_view_state and is skipped in seen-by).
    extra_viewer_ids = set(visitor_states) - approved_ids - {current_user.id}
    extra_viewers = await User.filter(id__in=extra_viewer_ids)

    return WorkspaceCollaboratorsResponse(
        collaborators=[_collaborator_response(c, "approved", view_state_for(c.model.user_id)) for c in presenter],
        pending=[_collaborator_response(c, "pending", view_state_for(c.model.user_id)) for c in presenter.pending],
        viewers=[
            WorkspaceViewerResponse(user=_user_response(u), view_state=_view_state_response(view_state_for(u.id)))
            for u in extra_viewers
        ],
        present_user_ids=[str(uid) for uid in present_user_ids],
        current_user_view_state=_view_state_response(view_state_for(current_user.id)),
    )


@router.get("/workspaces/{workspace_id}/collaborators", response_model=WorkspaceCollaboratorsResponse)
async def api_workspace_collaborators_index(
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    return await _build_response(workspace, current_user)


# Mention typeahead source for rich-text editors that aren't scoped to a single workspace
# (post drafts, document editor). Lists every active user in the org and marks none as
# collaborators since there is no workspace to scope against.
@router.get("/workspaces/collaborators/available", response_model=WorkspaceCollaboratorTypeaheadResponse)
async def api_workspace_collaborators_available(current_user: User = Depends(get_current_user)):
    users = await User.active.get_queryset().filter(organization_id=current_user.organization_id).all()
    return WorkspaceCollaboratorTypeaheadResponse(
        users=[
            WorkspaceCollaboratorTypeaheadUser(id=u.id, display_name=u.display_name, is_collaborator=False)
            for u in users
        ]
    )


# Mention typeahead source scoped to a workspace's current collaborators (chat/comment presets).
@router.get(
    "/workspaces/{workspace_id}/collaborators/typeahead",
    response_model=WorkspaceCollaboratorTypeaheadResponse,
)
async def api_workspace_collaborators_typeahead(
    workspace: Workspace = Depends(get_workspace), current_user: User = Depends(get_current_user)
):
    all_users = (
        await User.active.get_queryset().filter(User.filters.by_organization(current_user.organization_id)).all()
    )
    collaborator_ids = {u.id for u in await workspace.resource.collaboration.accessors.all()}
    users = [
        WorkspaceCollaboratorTypeaheadUser(
            id=user.id, display_name=user.display_name, is_collaborator=user.id in collaborator_ids
        )
        for user in all_users
    ]
    users.sort(key=lambda u: not u.is_collaborator)  # Collaborators first
    return WorkspaceCollaboratorTypeaheadResponse(users=users)


@router.post(
    "/workspaces/{workspace_id}/collaborators",
    response_model=WorkspaceCollaboratorsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_workspace_collaborators_create(
    body: WorkspaceCollaboratorAddRequest,
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    user = await User.get(id=body.user_id, organization_id=current_user.organization_id).prefetch_related(
        "oauth_tokens"
    )
    await add_collaborator(user, workspace, current_user, body.reason)
    return await _build_response(workspace, current_user)


@router.post(
    "/workspaces/{workspace_id}/collaborators/invite",
    response_model=WorkspaceCollaboratorsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_workspace_collaborators_invite(
    body: WorkspaceCollaboratorInviteRequest,
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    invite = await invite_and_add_collaborator(workspace, current_user, body.email, body.reason)
    if not invite.success or not invite.invited:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=invite.error or "There was a problem inviting this person.",
        )
    return await _build_response(workspace, current_user)


@router.delete("/workspaces/{workspace_id}/collaborators/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_workspace_collaborators_delete(
    user_id: UUID,
    workspace: Workspace = Depends(get_workspace),
):
    user = await User.get(id=user_id, organization_id=workspace.organization_id)
    await remove_collaborator(workspace, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/workspaces/{workspace_id}/collaborators/{collaborator_id}/approve",
    response_model=WorkspaceCollaboratorsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_workspace_collaborators_approve(
    collaborator: Collaborator = Depends(get_pending_collaborator),
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    await add_collaborator(collaborator.user, workspace, current_user, "Approving your access request")
    return await _build_response(workspace, current_user)


#
# Access Requests
#
#


async def _fetch_access_workspace(workspace_id: UUID, current_user: User) -> Workspace:
    # collaborators are prefetched because can_be_accessed_by walks the relation during POST.
    return await Workspace.get(id=workspace_id, organization_id=current_user.organization_id).prefetch_related(
        "collaborators"
    )


async def _existing_collaborator(workspace: Workspace, user: User) -> Collaborator | None:
    # The default manager filters to approved-only; pending access requests need .unscoped.
    return await Collaborator.unscoped.get_or_none(workspace_id=workspace.id, user_id=user.id)


@router.get(
    "/workspaces/{workspace_id}/collaborators/access",
    response_model=WorkspaceAccessRequestState,
)
async def api_workspace_collaborators_access_show(workspace_id: UUID, current_user: User = Depends(get_current_user)):
    workspace = await _fetch_access_workspace(workspace_id, current_user)
    collaborator = await _existing_collaborator(workspace, current_user)
    return WorkspaceAccessRequestState(
        workspace_id=workspace.id,
        resource_label=titleize(workspace.resource_type).lower(),
        request=WorkspaceAccessRequest(id=collaborator.id, created_at=collaborator.created_at)
        if collaborator
        else None,
    )


@router.post(
    "/workspaces/{workspace_id}/collaborators/access",
    response_model=WorkspaceAccessRequestSubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_workspace_collaborators_access_create(
    workspace_id: UUID,
    body: WorkspaceAccessRequestSubmit,
    response: Response,
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    workspace = await _fetch_access_workspace(workspace_id, current_user)
    await workspace.fetch_resource()

    existing = await _existing_collaborator(workspace, current_user)

    # Only direct the requestor at the resource if they can already read it; otherwise the
    # resource page would just bounce them through RequestAccessError back to this form.
    if workspace.resource.collaboration.can_be_accessed_by(current_user):
        redirect_url = str(helpers.url_for("gid_redirect", gid=workspace.resource_gid.to_param))
    else:
        redirect_url = None

    if existing:
        # Idempotent resubmit of a still-pending request: 200, not 201.
        response.status_code = status.HTTP_200_OK
        return WorkspaceAccessRequestSubmitResponse(
            request=WorkspaceAccessRequest(id=existing.id, created_at=existing.created_at),
            redirect_url=redirect_url,
        )

    notifier = Notifier(workspace.resource, current_user)
    async with notifier.record_and_notify(action=EventAction.REQUESTED_COLLABORATOR_ACCESS) as recording:
        collaborator = await Collaborator.create(
            workspace_id=workspace.id,
            user_id=current_user.id,
            status=CollaboratorStatus.PENDING,
            using_db=recording.using_db,
        )
        recording.event.details.update(
            {"requestor_display_name": current_user.display_name, "requestor_note": body.note}
        )
        await collaborator.save(using_db=recording.using_db)

    return WorkspaceAccessRequestSubmitResponse(
        request=WorkspaceAccessRequest(id=collaborator.id, created_at=collaborator.created_at),
        redirect_url=redirect_url,
    )


@handle_stream("workspace_collaborators")
async def handle_workspace_collaborators_json(channel: Channel, **data):
    # The topic carries three kinds of broadcasts: presence changes (carrying
    # `present_user_ids`), membership changes from Collaborator.add/remove (carrying
    # `created_collaborator_id` / `deleted_collaborator_id`), and view-state changes when a
    # collaborator records a visit (carrying `visit_user_id`). Map each to a distinct event so
    # the client can update presence in place vs. refetch the full collaborators payload.
    visit_user_id = data.get("visit_user_id")
    if visit_user_id:
        # Skip the visitor — their own tab already reflects the visit; everyone else refetches
        # to pick up the new view_state (drives goal "Seen by" + the collaborators panel).
        if str(visit_user_id) == str(channel.current_user.id):
            return
        await channel.send_event(ChannelEventResource.WORKSPACE_COLLABORATORS, ChannelEventAction.VIEW_STATE_CHANGED)
        return

    if "created_collaborator_id" in data:
        await channel.send_event(ChannelEventResource.WORKSPACE_COLLABORATORS, ChannelEventAction.CREATED)
        return
    if "deleted_collaborator_id" in data:
        await channel.send_event(ChannelEventResource.WORKSPACE_COLLABORATORS, ChannelEventAction.DELETED)
        return

    if isinstance(data.get("present_user_ids"), list):
        present_user_ids = data["present_user_ids"]
    else:
        workspace_id = channel.get_param("workspace_id")
        present_user_ids = await Presence(scope_key=workspace_scope_key(workspace_id)).get_active_user_ids()
    await channel.send_event(
        ChannelEventResource.WORKSPACE_COLLABORATORS,
        ChannelEventAction.UPDATED,
        present_user_ids=[str(uid) for uid in present_user_ids],
    )
