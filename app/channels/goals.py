from app.channels.dependencies import is_org_authorized
from app.models.accounts import User
from app.models.collaboration.live import Presence
from app.models.workspaces.goals import Goal

from .base import Channel, ChannelRouter


async def is_goal_authorized(channel: Channel) -> bool:
    goal = await Goal.get(id=channel.get_param("goal_id")).prefetch_related("workspace__collaborators__user")
    workspace = await goal.workspace
    resource = await workspace.fetch_resource()
    return resource.collaboration.can_be_accessed_by(channel.current_user)


def goal_channel_presence_scope_key(channel: Channel) -> str:
    return f"goals:{channel.get_param('organization_id')}:{channel.get_param('view')}"


async def get_present_users(channel: Channel, data: dict) -> list[User]:
    if "present_user_ids" in data and isinstance(data["present_user_ids"], list):
        present_user_ids = data["present_user_ids"]
    else:
        scope_key = goal_channel_presence_scope_key(channel)
        present_user_ids = await Presence(scope_key=scope_key).get_active_user_ids()

    return await User.filter(id__in=present_user_ids).select_related("avatar_file") if present_user_ids else []


async def ensure_goals_presence(channel: Channel):
    presence = Presence(scope_key=goal_channel_presence_scope_key(channel))
    present_user_ids = await presence.add_user(channel.current_user.id)
    await channel.topic.broadcast(present_user_ids=present_user_ids)


async def remove_goals_presence(channel: Channel):
    presence = Presence(scope_key=goal_channel_presence_scope_key(channel))
    present_user_ids = await presence.remove_user(channel.current_user.id)
    await channel.topic.broadcast(present_user_ids=present_user_ids)


router = ChannelRouter()


@router.on_subscribe("goals_presence")
async def goals_presence_subscribe(channel: Channel):
    if not is_org_authorized(channel):
        await channel.reject("Unauthorized access to goals presence.")
        return

    await channel.accept()
    await ensure_goals_presence(channel)


@router.on_keepalive("goals_presence")
async def goals_presence_keepalive(channel: Channel):
    await ensure_goals_presence(channel)


@router.on_unsubscribe("goals_presence")
async def goals_presence_unsubscribe(channel: Channel):
    if not is_org_authorized(channel):
        return

    await remove_goals_presence(channel)


@router.on_subscribe("goals_index")
async def goals_index_subscribe(channel: Channel):
    if not is_org_authorized(channel):
        await channel.reject("Unauthorized access to goals index.")
        return

    await channel.accept()


@router.on_subscribe("goal_timeline")
async def goal_timeline_subscribe(channel: Channel):
    if await is_goal_authorized(channel):
        await channel.accept()
    else:
        await channel.reject("Unauthorized access to goal timeline.")


@router.on_subscribe("goal_comments")
async def goal_comments_subscribe(channel: Channel):
    if await is_goal_authorized(channel):
        await channel.accept()
    else:
        await channel.reject("Unauthorized access to goal comments.")
