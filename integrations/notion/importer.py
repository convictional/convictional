from uuid import UUID

from tortoise import BaseDBAsyncClient
from tortoise.exceptions import DoesNotExist

from app.models.collaboration.live import LiveDocument
from app.models.workspaces.documents import Document
from config.enums import Sharing
from integrations.notion.models import NotionPage


async def ensure_document_for_page(
    page: NotionPage, *, organization_id: UUID, creator_id: UUID, db: BaseDBAsyncClient
) -> Document:
    """Create (or return) the Document for a Notion page WITHOUT writing content. Saving the
    Document mints its Workspace. Idempotent on `page.document_id`."""
    if page.document_id is not None:
        try:
            return await Document.get(id=page.document_id, using_db=db)
        except DoesNotExist:
            # The page points at a Document that no longer exists (e.g. deleted, or a demo/test
            # DB reseed). Fall through and recreate rather than failing the whole page sync.
            page.document_id = None

    document = Document(
        title=page.title or "Untitled",
        organization_id=organization_id,
        creator_id=creator_id,
        sharing=Sharing.PRIVATE,
    )
    await document.save(using_db=db)

    page.document_id = document.id
    await page.save(using_db=db)
    return document


async def write_document_content(document: Document, markdown: str, *, db: BaseDBAsyncClient) -> None:
    """Write the document's live content once, on first import. Re-syncs must not clobber edits,
    so write only when the document has no content yet."""
    if not markdown or not markdown.strip():
        return
    existing = await document.get_live_document_markdown()
    if existing:
        return
    await LiveDocument.set_initial_content(document.live_document_topic, markdown, using_db=db)
