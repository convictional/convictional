import pytest

from app.models.workspaces.documents import Document
from infra.db import transaction
from integrations.notion.importer import ensure_document_for_page, write_document_content
from tests.helpers.factories import create_notion_page, create_user


@pytest.mark.asyncio
async def test_ensure_document_creates_and_links_but_writes_no_content():
    user = await create_user()
    page = await create_notion_page(user_id=user.id, title="Quarterly Plan", content_text="# Heading\n\nbody")

    async with transaction() as db:
        document = await ensure_document_for_page(
            page, organization_id=user.organization_id, creator_id=user.id, db=db
        )

    await page.refresh_from_db()

    assert page.document_id == document.id
    assert document.title == "Quarterly Plan"
    assert document.organization_id == user.organization_id
    assert document.creator_id == user.id
    # The split means ensure_document_for_page mints the doc/workspace but seeds no content.
    assert document.workspace_id is not None
    assert await document.get_live_document_markdown() == ""


@pytest.mark.asyncio
async def test_ensure_document_is_idempotent_on_page_document_id():
    user = await create_user()
    page = await create_notion_page(user_id=user.id, title="Original")

    async with transaction() as db:
        first = await ensure_document_for_page(page, organization_id=user.organization_id, creator_id=user.id, db=db)

    page.title = "Renamed In Notion"
    await page.save()

    async with transaction() as db:
        second = await ensure_document_for_page(page, organization_id=user.organization_id, creator_id=user.id, db=db)

    assert first.id == second.id
    assert await Document.filter(notion_pages__id=page.id).count() == 1
    assert second.title == "Original"


@pytest.mark.asyncio
async def test_ensure_document_recreates_when_document_id_is_stale():
    # A page can point at a Document that no longer exists (deleted, or a demo/test DB reseed).
    # ensure_document_for_page must recreate it rather than raising DoesNotExist and failing sync.
    user = await create_user()
    page = await create_notion_page(user_id=user.id, title="Stale")

    async with transaction() as db:
        first = await ensure_document_for_page(page, organization_id=user.organization_id, creator_id=user.id, db=db)

    await Document.filter(id=first.id).delete()

    async with transaction() as db:
        second = await ensure_document_for_page(page, organization_id=user.organization_id, creator_id=user.id, db=db)

    await page.refresh_from_db()
    assert second.id != first.id
    assert page.document_id == second.id


@pytest.mark.asyncio
async def test_write_document_content_writes_once_and_never_clobbers():
    user = await create_user()
    page = await create_notion_page(user_id=user.id, title="Doc")

    async with transaction() as db:
        document = await ensure_document_for_page(
            page, organization_id=user.organization_id, creator_id=user.id, db=db
        )
        await write_document_content(document, "# First body", db=db)

    assert await document.get_live_document_markdown() == "# First body"

    # Re-seeding must not clobber the existing (possibly user-edited) content.
    async with transaction() as db:
        await write_document_content(document, "# Rewritten body", db=db)

    assert await document.get_live_document_markdown() == "# First body"


@pytest.mark.asyncio
async def test_write_document_content_no_op_for_empty_markdown():
    user = await create_user()
    page = await create_notion_page(user_id=user.id, title="Empty")

    async with transaction() as db:
        document = await ensure_document_for_page(
            page, organization_id=user.organization_id, creator_id=user.id, db=db
        )
        await write_document_content(document, "", db=db)

    assert await document.get_live_document_markdown() == ""
