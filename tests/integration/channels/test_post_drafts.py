import pytest

from config.enums import ChannelMessageType, Sharing
from infra.messaging import Topic
from tests.helpers.app import AppClient
from tests.helpers.factories import create_collaborator, create_post, create_user


@pytest.mark.asyncio
async def test_post_draft_access_control(client: AppClient):
    owner = await client.get_default_user()
    collaborator = await create_user(organization_id=owner.organization_id)
    unauthorized_user = await create_user(organization_id=owner.organization_id)

    draft = await create_post(
        creator_id=owner.id,
        organization_id=owner.organization_id,
        published_at=None,
        sharing=Sharing.PRIVATE,
    )
    await draft.fetch_related("workspace")
    await create_collaborator(
        user_id=collaborator.id, workspace_id=draft.workspace_id, organization_id=owner.organization_id
    )

    draft_topic = Topic("post_draft", post_id=draft.id)

    # Owner can subscribe
    client.current_user = owner
    async with client.connect_channel(draft_topic) as websocket:
        assert websocket is not None

    # Collaborator can subscribe
    client.current_user = collaborator
    async with client.connect_channel(draft_topic) as websocket:
        assert websocket is not None

    # Unauthorized user is rejected
    client.current_user = unauthorized_user
    with pytest.raises(Exception):
        async with client.connect_channel(draft_topic):
            pass

    # Missing post_id parameter is rejected
    with pytest.raises(Exception):
        async with client.connect_channel(Topic("post_draft")):
            pass


@pytest.mark.asyncio
async def test_post_draft_unsigned_subscribe_unauthorized(client: AppClient):
    """An unsigned subscribe with another org's post_id is rejected at subscribe time."""
    await client.get_default_user()
    other = await create_user(name="Other Org User")
    post = await create_post(
        creator_id=other.id, organization_id=other.organization_id, published_at=None, sharing=Sharing.PRIVATE
    )

    for stream in ("post_draft", "post_draft_comments"):
        async with client.connect_websocket("/channels") as websocket:
            await websocket.send_json(
                {
                    "type": ChannelMessageType.SUBSCRIBE,
                    "topic_stream": stream,
                    "topic_params": {"post_id": str(post.id)},
                }
            )
            response = await websocket.receive_json()
            assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
