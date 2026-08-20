import pytest

from config.enums import Sharing
from infra.messaging import Topic
from tests.helpers.app import AppClient
from tests.helpers.factories import create_collaborator, create_post, create_user


@pytest.mark.asyncio
async def test_post_comments_access_control(client: AppClient):
    owner = await client.get_default_user()
    collaborator = await create_user(organization_id=owner.organization_id)
    unauthorized_user = await create_user(organization_id=owner.organization_id)

    post = await create_post(
        creator_id=owner.id,
        organization_id=owner.organization_id,
        sharing=Sharing.PRIVATE,
    )
    await post.fetch_related("workspace")
    await create_collaborator(
        user_id=collaborator.id, workspace_id=post.workspace_id, organization_id=owner.organization_id
    )

    topic = Topic("post_comments", post_id=post.id)

    # Owner can subscribe
    client.current_user = owner
    async with client.connect_channel(topic) as websocket:
        assert websocket is not None

    # Collaborator can subscribe
    client.current_user = collaborator
    async with client.connect_channel(topic) as websocket:
        assert websocket is not None

    # Unauthorized user is rejected
    client.current_user = unauthorized_user
    with pytest.raises(Exception):
        async with client.connect_channel(topic):
            pass

    # Missing post_id parameter is rejected
    with pytest.raises(Exception):
        async with client.connect_channel(Topic("post_comments")):
            pass
