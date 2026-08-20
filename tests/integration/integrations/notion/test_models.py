import pytest
from tortoise.exceptions import IntegrityError

from config.enums import Integration
from integrations.notion.enums import NotionNodeKind
from integrations.notion.models import NotionConnection, NotionPage
from tests.helpers.factories import create_notion_connection, create_notion_page, create_user


@pytest.mark.asyncio
async def test_notion_connection_round_trip_and_user_integration_flag():
    user = await create_user()

    connection = await create_notion_connection(
        user_id=user.id,
        access_token="secret_abc123",
        workspace_id="ws-xyz",
        workspace_name="Engineering",
        bot_id="bot-1",
    )

    fetched = await NotionConnection.get(id=connection.id)
    assert fetched.access_token == "secret_abc123"
    assert fetched.workspace_id == "ws-xyz"
    assert fetched.workspace_name == "Engineering"
    assert fetched.bot_id == "bot-1"
    assert fetched.user_id == user.id

    assert not user.is_integrated_with(Integration.NOTION)
    await user.add_integration(Integration.NOTION)
    assert user.is_integrated_with(Integration.NOTION)
    await user.remove_integration(Integration.NOTION)
    assert not user.is_integrated_with(Integration.NOTION)


@pytest.mark.asyncio
async def test_notion_connection_unique_per_user():
    user = await create_user()
    await create_notion_connection(user_id=user.id)

    with pytest.raises(IntegrityError):
        await create_notion_connection(user_id=user.id)


@pytest.mark.asyncio
async def test_notion_page_unique_per_connection_and_cascade_delete():
    connection = await create_notion_connection()
    other_connection = await create_notion_connection()

    page = await create_notion_page(
        notion_connection_id=connection.id,
        notion_page_id="page-shared-id",
        title="Roadmap",
        content_text="Quarter plan",
    )
    assert page.is_selected_for_sync is False

    # Same notion_page_id is fine across different connections.
    await create_notion_page(
        notion_connection_id=other_connection.id,
        notion_page_id="page-shared-id",
    )

    # But duplicate within the same connection is rejected.
    with pytest.raises(IntegrityError):
        await create_notion_page(
            notion_connection_id=connection.id,
            notion_page_id="page-shared-id",
        )

    await connection.delete()
    assert await NotionPage.filter(notion_connection_id=connection.id).count() == 0
    assert await NotionPage.filter(notion_connection_id=other_connection.id).count() == 1


@pytest.mark.asyncio
async def test_notion_page_count_columns_default_to_zero():
    page = await create_notion_page()

    fetched = await NotionPage.get(id=page.id)
    assert fetched.kind == NotionNodeKind.PAGE
    assert fetched.parent_kind is None
    assert fetched.selected_descendant_count == 0
    assert fetched.total_descendant_count == 0


@pytest.mark.asyncio
async def test_notion_database_and_page_nodes_coexist_under_one_connection():
    connection = await create_notion_connection()

    database = await create_notion_page(
        notion_connection_id=connection.id,
        notion_page_id="database-node-id",
        title="Projects",
        kind=NotionNodeKind.DATABASE,
        parent_kind="workspace",
        total_descendant_count=3,
        selected_descendant_count=2,
    )
    leaf = await create_notion_page(
        notion_connection_id=connection.id,
        notion_page_id="page-leaf-id",
        title="Spec",
        kind=NotionNodeKind.PAGE,
        parent_notion_id="database-node-id",
        parent_kind=NotionNodeKind.DATABASE,
    )

    fetched_database = await NotionPage.get(id=database.id)
    assert fetched_database.kind == NotionNodeKind.DATABASE
    assert fetched_database.parent_kind == "workspace"
    assert fetched_database.total_descendant_count == 3
    assert fetched_database.selected_descendant_count == 2

    fetched_leaf = await NotionPage.get(id=leaf.id)
    assert fetched_leaf.kind == NotionNodeKind.PAGE
    assert fetched_leaf.parent_notion_id == "database-node-id"
    assert fetched_leaf.parent_kind == NotionNodeKind.DATABASE

    assert await NotionPage.filter(notion_connection_id=connection.id).count() == 2


@pytest.mark.asyncio
async def test_notion_node_unique_together_rejects_duplicate_node_ids():
    connection = await create_notion_connection()

    await create_notion_page(
        notion_connection_id=connection.id,
        notion_page_id="shared-node-id",
        kind=NotionNodeKind.DATABASE,
    )

    with pytest.raises(IntegrityError):
        await create_notion_page(
            notion_connection_id=connection.id,
            notion_page_id="shared-node-id",
            kind=NotionNodeKind.PAGE,
        )


@pytest.mark.asyncio
async def test_cascade_delete_drops_folder_and_leaf_rows_together():
    connection = await create_notion_connection()

    await create_notion_page(
        notion_connection_id=connection.id,
        notion_page_id="folder-node-id",
        kind=NotionNodeKind.DATABASE,
        parent_kind="workspace",
    )
    await create_notion_page(
        notion_connection_id=connection.id,
        notion_page_id="leaf-node-id",
        kind=NotionNodeKind.PAGE,
        parent_notion_id="folder-node-id",
        parent_kind=NotionNodeKind.DATABASE,
    )
    assert await NotionPage.filter(notion_connection_id=connection.id).count() == 2

    await connection.delete()
    assert await NotionPage.filter(notion_connection_id=connection.id).count() == 0
