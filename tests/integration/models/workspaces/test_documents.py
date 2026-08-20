import pytest

from app.models.collaboration.workspace import Collaborator, SubscriberResolver, Subscription
from config.enums import Sharing
from tests.helpers.factories import create_document, create_user


@pytest.mark.asyncio
async def test_organization_shared_document_does_not_subscribe_bystanders():
    # Documents don't broadcast: organization sharing is passive viewing access,
    # not a subscription opt-in, even with the default global SUBSCRIBED preference.
    creator = await create_user()
    bystander = await create_user(organization_id=creator.organization_id)

    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )
    await document.fetch_related("workspace")

    assert await Collaborator.get_or_none(workspace_id=document.workspace_id, user_id=bystander.id) is None
    assert await Subscription.get_or_none(workspace_id=document.workspace_id, subscriber_id=bystander.id) is None
    assert bystander not in await SubscriberResolver(workspace=document.workspace).resolve()
