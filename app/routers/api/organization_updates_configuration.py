from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.accounts import OrganizationUpdatesConfiguration, User
from app.models.workspaces.goals import Goal
from app.routers.api.schemas import UpdatesConfigurationResponse, UpdatesConfigurationUpdateRequest
from app.routers.dependencies import get_admin_user

router = APIRouter(tags=["organization"])


async def _has_open_goals(organization_id: UUID) -> bool:
    return await Goal.filter(Goal.filters.by_active_open_top_level(organization_id)).exists()


async def _get_or_build_config(organization_id: UUID) -> OrganizationUpdatesConfiguration:
    config = await OrganizationUpdatesConfiguration.get_or_none(organization_id=organization_id)
    if not config:
        config = OrganizationUpdatesConfiguration(organization_id=organization_id)
    return config


def _response(config: OrganizationUpdatesConfiguration, has_goals: bool) -> UpdatesConfigurationResponse:
    # Until a schedule is configured, the model's frequency/hour/day_of_week properties return
    # defaults (weekly/9/"1") that are indistinguishable from a real choice. Report null instead,
    # so "unconfigured" is unambiguous and the client supplies its own form placeholders.
    configured = config.update_schedule is not None
    return UpdatesConfigurationResponse(
        frequency=config.frequency if configured else None,
        hour=config.hour if configured else None,
        day_of_week=config.day_of_week if configured else None,
        goal_update_question=config.goal_update_question,
        has_goals=has_goals,
        enabled=bool(config.update_schedule and config.goal_update_question and has_goals),
    )


@router.get("/organization/updates_configuration", response_model=UpdatesConfigurationResponse)
async def api_organization_updates_configuration_show(current_user: User = Depends(get_admin_user)):
    config = await _get_or_build_config(current_user.organization_id)
    has_goals = await _has_open_goals(current_user.organization_id)
    return _response(config, has_goals)


@router.patch("/organization/updates_configuration", response_model=UpdatesConfigurationResponse)
async def api_organization_updates_configuration_update(
    body: UpdatesConfigurationUpdateRequest,
    current_user: User = Depends(get_admin_user),
):
    config = await _get_or_build_config(current_user.organization_id)

    # The schedule fields move together: building the cron needs both frequency and hour
    # (day_of_week only for weekly).
    if "frequency" in body.model_fields_set and "hour" in body.model_fields_set:
        if body.frequency is None or body.hour is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="frequency and hour are required to set the schedule",
            )
        if error := config.validate_schedule(body.frequency, body.hour, body.day_of_week):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error)
        config.set_schedule(body.frequency, body.hour, body.day_of_week)

    if "goal_update_question" in body.model_fields_set and body.goal_update_question is not None:
        config.goal_update_question = body.goal_update_question

    await config.save()

    has_goals = await _has_open_goals(current_user.organization_id)
    return _response(config, has_goals)
