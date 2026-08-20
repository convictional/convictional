import pytest

from app.models.workspaces.documents import DocumentComment
from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType, ReactionType, Sharing
from infra.messaging import Topic
from tests.helpers.app import AppClient
from tests.helpers.factories import create_collaborator, create_document, create_user


@pytest.mark.asyncio
async def test_document_comments_access_control(client: AppClient):
    owner = await client.get_default_user()
    collaborator = await create_user(organization_id=owner.organization_id)
    non_collaborator = await create_user(organization_id=owner.organization_id)

    document = await create_document(
        creator_id=owner.id,
        organization_id=owner.organization_id,
        sharing=Sharing.PRIVATE,
    )
    await document.fetch_related("workspace")
    await create_collaborator(
        user_id=collaborator.id, workspace_id=document.workspace_id, organization_id=owner.organization_id
    )

    topic = Topic("document_comments", document_id=document.id)

    # Owner can subscribe
    client.current_user = owner
    async with client.connect_channel(topic) as websocket:
        assert websocket is not None

    # Collaborator can subscribe
    client.current_user = collaborator
    async with client.connect_channel(topic) as websocket:
        assert websocket is not None

    # Non-collaborator is rejected
    client.current_user = non_collaborator
    with pytest.raises(Exception):
        async with client.connect_channel(topic):
            pass

    # Missing document_id parameter is rejected
    with pytest.raises(Exception):
        async with client.connect_channel(Topic("document_comments")):
            pass


@pytest.mark.asyncio
async def test_reaction_broadcast(client: AppClient):
    owner = await client.get_default_user()
    collaborator = await create_user(organization_id=owner.organization_id)

    document = await create_document(
        creator_id=owner.id,
        organization_id=owner.organization_id,
        sharing=Sharing.PRIVATE,
    )
    await document.fetch_related("workspace")
    await create_collaborator(
        user_id=collaborator.id, workspace_id=document.workspace_id, organization_id=owner.organization_id
    )

    comment = await DocumentComment.create(
        content="Test comment",
        quoted_text="text",
        comment_mark_id="mark-1",
        document_id=document.id,
        user_id=owner.id,
    )
    comment.toggle_reaction(owner.id, ReactionType.THUMBS_UP)
    await comment.save(update_fields=["reactions"])

    topic = Topic("document_comments", document_id=document.id)

    client.current_user = collaborator
    async with client.connect_channel(topic) as websocket:
        await topic.broadcast(updated_comment_id=str(comment.id))

        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.EVENT
        assert response["resource"] == ChannelEventResource.DOCUMENT_COMMENT
        assert response["action"] == ChannelEventAction.REACTION_TOGGLED
        assert response["data"]["comment_id"] == str(comment.id)
        reaction_ids = [u["id"] for u in response["data"]["reactions"]["thumbs_up"]]
        assert str(owner.id) in reaction_ids


@pytest.mark.asyncio
async def test_deleted_comment_handled_gracefully(client: AppClient):
    owner = await client.get_default_user()

    document = await create_document(
        creator_id=owner.id,
        organization_id=owner.organization_id,
    )
    await document.fetch_related("workspace")

    comment = await DocumentComment.create(
        content="Will be deleted",
        quoted_text="",
        comment_mark_id="mark-1",
        document_id=document.id,
        user_id=owner.id,
    )

    topic = Topic("document_comments", document_id=document.id)

    client.current_user = owner
    async with client.connect_channel(topic) as websocket:
        # Broadcast for a non-existent comment
        await topic.broadcast(updated_comment_id="00000000-0000-0000-0000-000000000000")

        # Verify channel still works by sending a valid broadcast
        await topic.broadcast(updated_comment_id=str(comment.id))

        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.EVENT
        assert response["data"]["comment_id"] == str(comment.id)


@pytest.mark.asyncio
async def test_document_unsigned_subscribe_unauthorized(client: AppClient):
    """An unsigned subscribe with another org's document_id is rejected at subscribe time."""
    await client.get_default_user()
    other = await create_user(name="Other Org User")
    document = await create_document(
        creator_id=other.id, organization_id=other.organization_id, sharing=Sharing.PRIVATE
    )

    for stream in ("document", "document_comments"):
        async with client.connect_websocket("/channels") as websocket:
            await websocket.send_json(
                {
                    "type": ChannelMessageType.SUBSCRIBE,
                    "topic_stream": stream,
                    "topic_params": {"document_id": str(document.id)},
                }
            )
            response = await websocket.receive_json()
            assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
