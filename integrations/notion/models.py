from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from tortoise import BaseDBAsyncClient, fields

from app.models.accounts import User
from app.models.workspaces.documents import Document
from infra.db import RecordModel
from integrations.notion.enums import NotionNodeKind


class NotionConnection(RecordModel):
    access_token = fields.TextField(description="protected_column")
    workspace_id: str | None = fields.TextField(null=True)
    workspace_name: str | None = fields.TextField(null=True)
    bot_id = fields.TextField(null=True)

    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "convictional.User", related_name="notion_connections", on_delete=fields.CASCADE
    )
    user_id: Annotated[UUID, "foreign key to user"]

    pages: fields.ReverseRelation["NotionPage"]

    class Meta:
        ordering = ["-created_at"]
        unique_together = (("user_id",),)


class NotionPage(RecordModel):
    notion_page_id = fields.TextField()
    title = fields.TextField(null=True)
    kind = fields.CharEnumField(NotionNodeKind, default=NotionNodeKind.PAGE, max_length=255)
    # Stores the normalized parent id (data_source -> database id; block -> resolved containing page id).
    parent_notion_id = fields.TextField(null=True)
    parent_kind = fields.TextField(null=True)  # "page" | "database" | "workspace" | None
    notion_last_edited_time = fields.DatetimeField(null=True)
    last_synced_at = fields.DatetimeField(null=True)
    is_selected_for_sync = fields.BooleanField(default=False)
    selected_descendant_count = fields.IntField(default=0)
    total_descendant_count = fields.IntField(default=0)
    # True once a full subtree resolution (the cascade job) has run for this node, so the
    # denormalized counts above can be trusted for tri-state rendering.
    counts_authoritative = fields.BooleanField(default=False)
    content_text = fields.TextField(null=True)

    # Intentionally denormalized from notion_connection.user_id (one connection per
    # user today) so pages can be filtered by user without joining the connection.
    # No DB-level constraint keeps them in sync — every create path MUST source this
    # from the parent connection's user_id, never set it independently.
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "convictional.User", related_name="notion_pages", on_delete=fields.CASCADE
    )
    user_id: Annotated[UUID, "foreign key to user"]

    notion_connection: fields.ForeignKeyRelation[NotionConnection] = fields.ForeignKeyField(
        "convictional.NotionConnection", related_name="pages", on_delete=fields.CASCADE
    )
    notion_connection_id: Annotated[UUID, "foreign key to notion connection"]

    document: fields.ForeignKeyNullableRelation["Document"] = fields.ForeignKeyField(
        "convictional.Document", related_name="notion_pages", null=True, on_delete=fields.SET_NULL
    )
    document_id: Annotated[UUID | None, "foreign key to the imported Convictional Document"]

    class Meta:
        ordering = ["-updated_at"]
        indexes = (
            ("user_id",),
            ("notion_connection_id",),
        )
        unique_together = (("notion_connection_id", "notion_page_id"),)

    async def mark_inaccessible(self, using_db: BaseDBAsyncClient | None = None) -> None:
        # The page returned 404 (deleted or the integration lost access). Blank the cached
        # content so a stale copy isn't served, and stamp the sync time as the last attempt.
        self.content_text = ""
        self.last_synced_at = datetime.now(UTC)
        await self.save(update_fields=["content_text", "last_synced_at"], using_db=using_db)

    @classmethod
    async def mark_inaccessible_bulk(
        cls,
        *,
        notion_connection_id: UUID,
        notion_page_ids: Iterable[str],
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        # Set-based variant of mark_inaccessible for the cascade walk: blank cached content and
        # stamp the sync time for every newly-inaccessible node in one query, without loading rows.
        ids = list(notion_page_ids)
        if not ids:
            return
        await (
            cls.filter(notion_connection_id=notion_connection_id, notion_page_id__in=ids)
            .using_db(using_db)
            .update(content_text="", last_synced_at=datetime.now(UTC))
        )

    @staticmethod
    def effective_kind(client_kind: str | None, saved_page: "NotionPage | None") -> str:
        # Resolve a node's kind for child-traversal / cascade dispatch. Trust the client-supplied
        # kind when it's valid — it knows the node even before it's persisted, and a top-tier node
        # isn't saved until it's expanded or selected, so the DB can't always tell us. Fall back to
        # the stored row, then to "page" (pages, not databases, are the common unsaved top-tier node).
        valid_kinds = {NotionNodeKind.PAGE.value, NotionNodeKind.DATABASE.value}
        if client_kind in valid_kinds:
            return client_kind
        if saved_page is not None:
            return NotionNodeKind(saved_page.kind).value
        return NotionNodeKind.PAGE.value

    @classmethod
    async def refresh_parent_leaf_counts(
        cls,
        *,
        notion_connection_id: UUID,
        parent: "NotionPage",
        using_db: BaseDBAsyncClient,
    ) -> None:
        # Incremental, single-level refresh on expansion: count the leaf pages known directly under
        # the parent. Converges toward the authoritative count the cascade writes; expansion alone
        # never claims authority (counts_authoritative is left as-is).
        children = await cls.filter(
            notion_connection_id=notion_connection_id,
            parent_notion_id=parent.notion_page_id,
            kind=NotionNodeKind.PAGE.value,
        ).using_db(using_db)
        parent.total_descendant_count = len(children)
        parent.selected_descendant_count = sum(1 for child in children if child.is_selected_for_sync)
        await parent.save(using_db=using_db)

    @classmethod
    async def refresh_descendant_counts(
        cls,
        *,
        notion_connection_id: UUID,
        authoritative_ids: set[str],
        root_notion_id: str,
        using_db: BaseDBAsyncClient,
    ) -> None:
        # Rebuild the denormalized descendant counts from the persisted adjacency list. The caller
        # (the cascade job) walked `authoritative_ids` in full, so every node in that set gets exact
        # counts and becomes authoritative. Ancestors up to the workspace root are refreshed too, but
        # never claim authority — only one of their branches was walked, so other branches are unknown.
        # Project only the columns the roll-up reads/writes so the unbounded content_text and other
        # unused fields stay out of memory while up to CASCADE_MAX_NODES rows are held under the lock.
        # These stay full model instances (not .values() dicts) because bulk_update needs the pk and
        # attribute access on each object.
        pages = await (
            cls.filter(notion_connection_id=notion_connection_id)
            .only(
                "id",
                "notion_page_id",
                "parent_notion_id",
                "kind",
                "is_selected_for_sync",
                "selected_descendant_count",
                "total_descendant_count",
                "counts_authoritative",
            )
            .using_db(using_db)
        )
        by_id = {page.notion_page_id: page for page in pages}
        children_by_parent: dict[str, list[NotionPage]] = {}
        for page in pages:
            if page.parent_notion_id is not None:
                children_by_parent.setdefault(page.parent_notion_id, []).append(page)

        # Memoized post-order roll-up so a deep subtree is O(n), not O(n²) across per-node calls.
        # `stack` guards against cycles in the DAG (a back-edge contributes nothing).
        memo: dict[str, tuple[int, int]] = {}

        def leaf_counts(node_id: str, stack: set[str]) -> tuple[int, int]:
            if node_id in memo:
                return memo[node_id]
            if node_id in stack:
                return 0, 0
            stack.add(node_id)
            total = 0
            selected = 0
            for child in children_by_parent.get(node_id, []):
                if child.kind == NotionNodeKind.PAGE.value:
                    total += 1
                    if child.is_selected_for_sync:
                        selected += 1
                child_selected, child_total = leaf_counts(child.notion_page_id, stack)
                selected += child_selected
                total += child_total
            stack.discard(node_id)
            memo[node_id] = (selected, total)
            return selected, total

        # Resolved subtree: every walked node (root included). Ancestors: the chain above the root.
        subtree_ids = set(authoritative_ids)
        ancestor_ids: list[str] = []
        seen: set[str] = set(subtree_ids)
        root = by_id.get(root_notion_id)
        current: str | None = root.parent_notion_id if root is not None else None
        while isinstance(current, str) and current not in seen:
            seen.add(current)
            ancestor_ids.append(current)
            ancestor = by_id.get(current)
            current = ancestor.parent_notion_id if ancestor else None

        to_update: list[NotionPage] = []
        for node_id in subtree_ids:
            target = by_id.get(node_id)
            if target is None:
                continue
            target.selected_descendant_count, target.total_descendant_count = leaf_counts(node_id, set())
            target.counts_authoritative = True
            to_update.append(target)
        for node_id in ancestor_ids:
            target = by_id.get(node_id)
            if target is None:
                continue
            target.selected_descendant_count, target.total_descendant_count = leaf_counts(node_id, set())
            to_update.append(target)

        if to_update:
            await cls.bulk_update(
                to_update,
                fields=["selected_descendant_count", "total_descendant_count", "counts_authoritative"],
                using_db=using_db,
            )
