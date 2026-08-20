import pytest

from app.models.workspaces.documents import Document
from app.organization_setup import GETTING_STARTED_DOC_TITLE, populate_new_organization
from config.enums import Sharing
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_populate_new_organization_seeds_private_getting_started_doc():
    creator = await create_user()

    await populate_new_organization(creator)

    docs = await Document.filter(organization_id=creator.organization_id)
    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == GETTING_STARTED_DOC_TITLE
    assert doc.creator_id == creator.id
    # Must be private to match the copy the doc itself teaches ("Every doc starts private to you").
    assert doc.sharing == Sharing.PRIVATE

    markdown = await doc.get_live_document_markdown()
    assert "Every doc starts private to you" in markdown
