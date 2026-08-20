from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from app.models.accounts import User
from config import logger
from config.enums import JobQueue
from config.logging import LoggingContext
from infra.db import transaction
from infra.jobs import JobDefinition
from integrations.notion.blocks_to_text import blocks_to_text
from integrations.notion.client import NotionAPIError, NotionAuthError, NotionClient
from integrations.notion.enums import NotionNodeKind
from integrations.notion.importer import ensure_document_for_page, write_document_content
from integrations.notion.models import NotionConnection, NotionPage

# Defensive ceiling so a pathological/looping subtree cannot fan out unbounded under the
# 3 RPS budget. A cascade that hits this is logged and stops descending further.
CASCADE_MAX_NODES = 5000


class SyncNotionPagesJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    user_id: UUID

    async def perform(self):
        connection = await NotionConnection.get_or_none(user_id=self.user_id)
        if connection is None:
            # The integration was disconnected between enqueue and run. Benign race.
            logger.warning("Notion sync skipped: no connection for user")
            return

        user = await User.get(id=self.user_id)

        # The kind="page" guard is a backstop: a mis-flagged folder (database) row can never
        # reach ensure_document_for_page, even if something flips its is_selected_for_sync.
        selected_pages = await NotionPage.filter(
            notion_connection_id=connection.id,
            kind=NotionNodeKind.PAGE.value,
            is_selected_for_sync=True,
        )
        total = len(selected_pages)
        logger.info(f"Notion sync starting for {total} selected pages")

        synced = 0
        async with NotionClient(connection.access_token) as client:
            for page in selected_pages:
                with LoggingContext(notion_page_id=page.notion_page_id):
                    try:
                        await self._sync_page(client, page, user)
                        synced += 1
                    except NotionAuthError:
                        # Token is invalid — every subsequent page would fail the same way.
                        logger.warning("Notion token invalid; user must reconnect")
                        break
                    except NotionAPIError as exc:
                        if exc.status_code == 404:
                            await page.mark_inaccessible()
                            logger.warning("Notion page inaccessible (404)")
                        else:
                            logger.exception("Notion API error while syncing page")
                    except Exception:
                        logger.exception("Unexpected error while syncing Notion page")

        logger.info(f"Notion sync complete: {synced}/{total} pages")

    async def _sync_page(self, client: NotionClient, page: NotionPage, user: User) -> None:
        metadata = await client.get_page(page.notion_page_id)
        blocks = [block async for block in client.walk_page_blocks(page.notion_page_id)]

        # Apply the refreshed title before creating the document so a first-import doc is named
        # from current Notion metadata, not the stale page row.
        page.title = metadata.title or page.title
        if metadata.parent_id is not None:
            page.parent_notion_id = metadata.parent_id
        if metadata.last_edited_time is not None:
            page.notion_last_edited_time = metadata.last_edited_time

        async with transaction() as db:
            document = await ensure_document_for_page(
                page, organization_id=user.organization_id, creator_id=user.id, db=db
            )
            content_text = blocks_to_text(blocks)
            page.content_text = content_text
            page.last_synced_at = datetime.now(UTC)
            await page.save(using_db=db)
            await write_document_content(document, content_text, db=db)


@dataclass
class _DiscoveredNode:
    node_id: str
    kind: str
    title: str | None
    parent_id: str | None
    parent_kind: str | None


@dataclass
class _SubtreeResolution:
    # Selectable leaf page ids found anywhere under the resolved node (the node itself
    # included when it is a page). These are the only rows that get is_selected_for_sync set.
    leaf_page_ids: set[str] = field(default_factory=set)
    # Every node (folders + leaves) discovered during the walk, keyed by node_id, so the
    # tree and its denormalized counts have them on the next expansion.
    discovered: dict[str, _DiscoveredNode] = field(default_factory=dict)
    # Node ids that 404'd mid-walk; their rows are marked inaccessible like the sync path.
    inaccessible_ids: set[str] = field(default_factory=set)


class CascadeNotionSelectionJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    # The connection is resolved by user_id because Notion ids are only unique within a connection.
    user_id: UUID
    node_id: str
    kind: NotionNodeKind
    selected: bool

    async def perform(self):
        connection = await NotionConnection.get_or_none(user_id=self.user_id)
        if connection is None:
            # Disconnected between enqueue and run. Benign race — nothing to snapshot.
            logger.warning("Notion cascade skipped: no connection for user")
            return

        with LoggingContext(notion_node_id=self.node_id, kind=self.kind, selected=self.selected):
            async with NotionClient(connection.access_token) as client:
                resolution = await self._resolve_subtree(client)

            # Steps 4-5 are atomic and serialized per connection so concurrent cascades cannot
            # interleave their wholesale set/clear and produce inconsistent counts. The network
            # walk above runs lock-free so it never pins a Postgres connection for its duration.
            async with transaction() as db:
                await self._acquire_connection_lock(connection.id, db)
                await self._upsert_discovered(connection, resolution, db)
                await NotionPage.mark_inaccessible_bulk(
                    notion_connection_id=connection.id,
                    notion_page_ids=resolution.inaccessible_ids,
                    using_db=db,
                )
                await self._apply_selection(connection, resolution, db)
                await self._refresh_counts(connection, resolution, db)

            logger.info(
                "Notion cascade complete",
                extra={"leaf_count": len(resolution.leaf_page_ids)},
            )

    async def _resolve_subtree(self, client: NotionClient) -> _SubtreeResolution:
        resolution = _SubtreeResolution()
        seen: set[str] = set()
        await self._walk_node(
            client,
            node_id=self.node_id,
            kind=self.kind,
            parent_id=None,
            parent_kind=None,
            title=None,
            resolution=resolution,
            seen=seen,
        )
        return resolution

    async def _walk_node(
        self,
        client: NotionClient,
        *,
        node_id: str,
        kind: str,
        parent_id: str | None,
        parent_kind: str | None,
        title: str | None,
        resolution: _SubtreeResolution,
        seen: set[str],
    ) -> None:
        if node_id in seen:
            return  # Cycle / shared node already walked.
        if len(seen) >= CASCADE_MAX_NODES:
            logger.warning("Notion cascade hit fan-out cap; stopping descent")
            return
        seen.add(node_id)

        resolution.discovered[node_id] = _DiscoveredNode(
            node_id=node_id,
            kind=kind,
            title=title,
            parent_id=parent_id,
            parent_kind=parent_kind,
        )

        try:
            if kind == NotionNodeKind.DATABASE.value:
                await self._walk_database(client, node_id, resolution, seen)
            else:
                resolution.leaf_page_ids.add(node_id)
                await self._walk_page(client, node_id, resolution, seen)
        except NotionAPIError as exc:
            if exc.status_code == 404:
                resolution.inaccessible_ids.add(node_id)
                resolution.leaf_page_ids.discard(node_id)
                logger.warning("Notion node inaccessible during cascade (404)")
            else:
                raise

    async def _walk_page(
        self,
        client: NotionClient,
        page_id: str,
        resolution: _SubtreeResolution,
        seen: set[str],
    ) -> None:
        cursor: str | None = None
        while True:
            child_page = await client.list_child_nodes(page_id, cursor=cursor)
            for child in child_page.nodes:
                await self._walk_node(
                    client,
                    node_id=child.node_id,
                    kind=child.kind,
                    parent_id=page_id,
                    parent_kind=NotionNodeKind.PAGE.value,
                    title=child.title,
                    resolution=resolution,
                    seen=seen,
                )
            if not child_page.has_more:
                return
            cursor = child_page.next_cursor

    async def _walk_database(
        self,
        client: NotionClient,
        database_id: str,
        resolution: _SubtreeResolution,
        seen: set[str],
    ) -> None:
        database = await client.get_database(database_id)
        for source in database.data_sources:
            cursor: str | None = None
            while True:
                query_page = await client.query_data_source(source.data_source_id, cursor=cursor)
                for row in query_page.rows:
                    row_id = row.get("id")
                    if not isinstance(row_id, str):
                        continue
                    # Each database row is itself a selectable leaf page, and may parent sub-pages
                    # via its block-children, so recurse into it as a page.
                    await self._walk_node(
                        client,
                        node_id=row_id,
                        kind=NotionNodeKind.PAGE.value,
                        parent_id=database_id,
                        parent_kind=NotionNodeKind.DATABASE.value,
                        title=row_title(row),
                        resolution=resolution,
                        seen=seen,
                    )
                if not query_page.has_more:
                    break
                cursor = query_page.next_cursor

    async def _acquire_connection_lock(self, connection_id: UUID, db) -> None:
        # _apply_selection + _refresh_counts is a read-modify-write over the connection's whole page
        # set: it flips is_selected_for_sync, then recomputes every node's denormalized descendant
        # counts from the full adjacency list. Under READ COMMITTED, two cascades for the same
        # connection (e.g. a quick select then deselect of overlapping folders) can each recompute
        # counts from a snapshot predating the other's selection write and clobber it on commit,
        # leaving the stored counts disagreeing with the actual selection flags. Row locks don't
        # help — the recompute reads rows it never writes (ancestors, sibling branches) and each
        # cascade touches a different, overlapping set — so we serialize the whole set-then-recount
        # section with one connection-scoped advisory lock. It's xact-scoped (auto-released on
        # commit/rollback) and keyed per connection, so other connections' cascades still run freely.
        await db.execute_query("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", [str(connection_id)])

    async def _upsert_discovered(
        self,
        connection: NotionConnection,
        resolution: _SubtreeResolution,
        db,
    ) -> None:
        if not resolution.discovered:
            return

        existing = await NotionPage.filter(
            notion_connection_id=connection.id,
            notion_page_id__in=list(resolution.discovered.keys()),
        ).using_db(db)
        existing_by_id = {page.notion_page_id: page for page in existing}

        for node in resolution.discovered.values():
            page = existing_by_id.get(node.node_id)
            if page is None:
                await NotionPage.create(
                    notion_page_id=node.node_id,
                    title=node.title,
                    kind=node.kind,
                    parent_notion_id=node.parent_id,
                    parent_kind=node.parent_kind,
                    user_id=connection.user_id,
                    notion_connection_id=connection.id,
                    using_db=db,
                )
                continue

            page.kind = NotionNodeKind(node.kind)
            if node.title is not None:
                page.title = node.title
            # The resolved root keeps its existing parent linkage (we walked from it, not into it);
            # discovered descendants get their normalized parent edge written.
            if node.node_id != self.node_id and node.parent_id is not None:
                page.parent_notion_id = node.parent_id
                if node.parent_kind is not None:
                    page.parent_kind = node.parent_kind
            await page.save(using_db=db)

    async def _apply_selection(
        self,
        connection: NotionConnection,
        resolution: _SubtreeResolution,
        db,
    ) -> None:
        if not resolution.leaf_page_ids:
            return
        # Scoped to kind="page" so a folder row is never flagged for sync, and applied wholesale
        # (lossy, last-action-wins — no provenance).
        await (
            NotionPage.filter(
                notion_connection_id=connection.id,
                kind=NotionNodeKind.PAGE.value,
                notion_page_id__in=list(resolution.leaf_page_ids),
            )
            .using_db(db)
            .update(is_selected_for_sync=self.selected)
        )

    async def _refresh_counts(self, connection: NotionConnection, resolution: _SubtreeResolution, db) -> None:
        # The resolved subtree was walked in full, so its nodes get authoritative counts; the model
        # rolls up the whole connection's adjacency list and refreshes ancestors without authority.
        await NotionPage.refresh_descendant_counts(
            notion_connection_id=connection.id,
            authoritative_ids=set(resolution.discovered.keys()),
            root_notion_id=self.node_id,
            using_db=db,
        )


def row_title(row: dict) -> str | None:
    properties = row.get("properties")
    if not isinstance(properties, dict):
        return None
    for prop in properties.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            rich_text = prop.get("title") or []
            return "".join(item.get("plain_text", "") for item in rich_text if isinstance(item, dict)) or None
    return None
