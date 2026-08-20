from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from app.models.accounts import User
from app.models.collaboration.workspace import SubscriberResolver, Subscription, SubscriptionState, Workspace
from app.routers.api.schemas import SubscriptionResponse, SubscriptionUpdateRequest
from app.routers.dependencies import get_current_user, get_workspace

router = APIRouter(tags=["workspace subscriptions"])


def _response(state: SubscriptionState) -> SubscriptionResponse:
    return SubscriptionResponse(wants_all=state.wants_all, is_explicit=state.is_explicit)


async def _resolve(workspace: Workspace, user_id) -> SubscriptionState:
    return await SubscriberResolver(workspace=workspace).state_for(user_id)


@router.get("/workspaces/{workspace_id}/subscription", response_model=SubscriptionResponse)
async def api_workspace_subscription_show(
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    return _response(await _resolve(workspace, current_user.id))


@router.patch("/workspaces/{workspace_id}/subscription", response_model=SubscriptionResponse)
async def api_workspace_subscription_update(
    body: SubscriptionUpdateRequest,
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    row = await workspace.subscription_for(current_user.id)
    row.level = body.level
    await row.save()
    return _response(await _resolve(workspace, current_user.id))


@router.delete("/workspaces/{workspace_id}/subscription", status_code=status.HTTP_204_NO_CONTENT)
async def api_workspace_subscription_delete(
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    await Subscription.filter(workspace_id=workspace.id, subscriber_id=current_user.id).delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
