from tortoise import BaseDBAsyncClient

from app.models.accounts import User
from app.models.collaboration.live import LiveDocument
from app.models.workspaces.documents import Document
from config.enums import Sharing

# Starter content created once, when an organization's first user signs in. We deliberately
# don't seed a General group anymore — the chat index nudges the first user to create their
# own, so groups feel authored rather than pre-filled. Only the getting-started document is
# seeded, so the onboarding focus has something concrete to point at.
GETTING_STARTED_DOC_TITLE = "You should read this"
GETTING_STARTED_DOC_BODY = """\
This is a doc, and the fastest way to learn docs is to poke at this one. Edit it, format it, break it. Here's the quick tour.

## Formatting

Everything formats as you type. This sentence has **bold**, *italic*, and `inline code`, and you can drop in a [link](/documents).

> Pull a line out as a quote when it earns the emphasis.

Build structure with headings and lists:

- Start a bullet with a dash
- Type `1.` for a numbered list
- Type `[ ]` for a checklist

## Zen mode

Writing something real? Expand the doc into zen mode from the toolbar. The rest of the app falls away and it's just you and the page. Press Escape to come back.

## Comments

Select any text to leave a comment. Comments stay pinned to the exact words they're about, so feedback never drifts off into a separate thread.

## Private and shared docs in research

Every doc starts private to you. Share one to your organization and it joins the shared knowledge that research reads and cites when anyone asks a question. Keep it private and it stays yours alone. You decide what becomes part of the company brain.

## Try it now

1. Make a word **bold**, or turn a line into a heading.
2. Select a sentence and leave a comment on it.
3. Open zen mode from the toolbar, then press Escape to return.
4. When you're ready, delete this doc and start one of your own.
"""


async def populate_new_organization(creator: User, *, using_db: BaseDBAsyncClient | None = None) -> None:
    """Seed a brand-new organization's starter content for its first user.

    Runs once, in the is_new_organization branch of get_or_create_user. Creates only the
    getting-started document; groups are left for the creator to make from the chat index.
    """
    document = Document(
        title=GETTING_STARTED_DOC_TITLE,
        organization_id=creator.organization_id,
        creator_id=creator.id,
        # Private, to match the doc body ("Every doc starts private to you").
        sharing=Sharing.PRIVATE,
    )
    await document.save(using_db=using_db)
    await LiveDocument.set_initial_content(document.live_document_topic, GETTING_STARTED_DOC_BODY, using_db=using_db)
