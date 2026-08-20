import pytest

from config.enums import ChannelEventResource
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_scheduled_research_subscribe_rejects_other_user(client: AppClient):
    other = await create_user()
    topic = Topic("scheduled_research", user_id=str(other.id))

    await client.get_default_user()
    with pytest.raises(Exception):
        async with client.connect_channel(topic):
            pass


@pytest.mark.asyncio
async def test_scheduled_research_subscribe_accepts_current_user(client: AppClient):
    # The connect_channel helper asserts SUBSCRIPTION_CONFIRMED after connecting, so reaching the body
    # at all proves the subscribe handler accepted. An exception here would fail the test.
    user = await client.get_default_user()
    topic = Topic("scheduled_research", user_id=str(user.id))

    async with client.connect_channel(topic) as websocket:
        assert websocket is not None


@pytest.mark.asyncio
async def test_scheduled_research_preview_rejects_mismatched_user_in_topic(client: AppClient):
    other = await create_user()
    # Signed topic claims a different user → handler rejects
    topic = Topic("scheduled_research_preview", preview_id="pv-1", user_id=str(other.id))

    await client.get_default_user()
    with pytest.raises(Exception):
        async with client.connect_channel(topic):
            pass


@pytest.mark.asyncio
async def test_scheduled_research_preview_accept_for_current_user_broadcasts_error_on_missing_cache(client: AppClient):
    user = await client.get_default_user()
    topic = Topic("scheduled_research_preview", preview_id="nonexistent-id", user_id=str(user.id))

    async with client.connect_channel(topic) as websocket:
        # On subscribe, the channel accepts, then the on_subscribe handler broadcasts action=start.
        # The @handle_stream in the router reads the cache entry and, since it's missing, forwards an error event.
        response = await receive_event(websocket, ChannelEventResource.SCHEDULED_RESEARCH_PREVIEW)
        assert response["data"]["preview_action"] == "error"
