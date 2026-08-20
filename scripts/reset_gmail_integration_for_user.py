"""Reset a single user's Gmail integration and delete their email data.

Moved from `ResetGmailIntegrationForUserJob` because this is a maintenance
operation that should not be runnable from the /background_jobs UI.
"""

import argparse
import asyncio
from typing import cast

from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from app.models.accounts import User
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Attachment, Collaborator, Event, Mention, Subscription, Visit
from app.models.workspaces.email.contact import EmailContact
from app.models.workspaces.email.thread import EmailAttachment, EmailMessage, EmailThread, EmailThreadComment
from config.enums import AuthenticationProvider, Integration
from infra.db import RecordModel, transaction
from integrations.google.gmail import get_google_api_client
from integrations.google.models import GmailAccount
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES
from scripts.helpers import green_text, in_app_lifespan, red_text, yellow_text


async def batch_delete(model: type[RecordModel], where: Q, unscoped: bool = False, batch_size: int = 100) -> int:
    """Repeatedly SELECT a small page of IDs and DELETE those IDs.

    Each DELETE is a single statement => single implicit tx.
    """
    total = 0
    queryset: type[RecordModel] | QuerySet = model
    if unscoped:
        queryset = model.unscoped.get_queryset()

    while True:
        ids = await queryset.filter(where).limit(batch_size).values_list("id", flat=True)
        if not ids:
            break
        total += await queryset.filter(id__in=list(ids)).delete()
    return total


async def reset():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email", help="Email of the user whose Gmail integration should be reset.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required to actually perform the reset. Without this flag the script only prints what it would do.",
    )
    args = parser.parse_args()

    user = await User.get_or_none(email=args.email).prefetch_related("oauth_tokens")
    if not user:
        print(red_text(f"User {args.email} not found"))
        return

    print(
        yellow_text(
            f"About to remove Gmail integration for {args.email}, stop their watch, and delete all of their "
            f"email threads, messages, attachments, contacts, and mailbox entries. THIS IS IRREVERSIBLE."
        )
    )
    if not args.yes:
        print(red_text("Aborting: pass --yes to actually run."))
        return

    gmail_account = await GmailAccount.get_or_none(GmailAccount.filters.by_user(user.id))

    google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    if google_token and user.is_integrated_with(Integration.GMAIL):
        if gmail_account:
            google = await get_google_api_client(user, gmail_account)
            await google.stop_watch()

        async with transaction() as connection:
            await google_token.remove_scopes(GOOGLE_GMAIL_SCOPES, using_db=connection)
            await user.remove_integration(Integration.GMAIL, using_db=connection)
            await GmailAccount.filter(GmailAccount.filters.by_user(user.id)).using_db(connection).delete()

    email_threads = cast(
        list[EmailThread],
        await EmailThread.unscoped.get_queryset().filter(EmailThread.filters.by_creator(user.id)),
    )

    thread_ids = [thread.id for thread in email_threads]
    workspace_ids = [thread.workspace_id for thread in email_threads]

    if not thread_ids:
        print(green_text(f"No email threads to delete for {args.email}."))
        return

    await EmailContact.filter(EmailContact.filters.by_user(user.id)).delete()

    await batch_delete(EmailAttachment, where=Q(thread_id__in=thread_ids))
    await batch_delete(EmailMessage, where=Q(thread_id__in=thread_ids), unscoped=True)
    await batch_delete(MailboxEntry, where=MailboxEntry.filters.by_owner(user.id), unscoped=True)

    if workspace_ids:
        await batch_delete(Visit, where=Q(workspace_id__in=workspace_ids))
        await batch_delete(Mention, where=Q(workspace_id__in=workspace_ids))
        await batch_delete(Subscription, where=Q(workspace_id__in=workspace_ids))
        await batch_delete(Event, where=Q(workspace_id__in=workspace_ids))
        await batch_delete(Collaborator, where=Q(workspace_id__in=workspace_ids))
        await batch_delete(Attachment, where=Q(workspace_id__in=workspace_ids))
        await batch_delete(EmailThreadComment, where=Q(email_thread_id__in=thread_ids))

    await batch_delete(EmailThread, where=Q(id__in=thread_ids), unscoped=True)

    print(green_text(f"Gmail integration reset for {args.email}."))


if __name__ == "__main__":
    asyncio.run(in_app_lifespan(reset()))
