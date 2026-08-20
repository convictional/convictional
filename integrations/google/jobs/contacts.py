from datetime import UTC, datetime
from uuid import UUID

from fastapi import status
from googleapiclient.errors import HttpError

from app.jobs.content import ContentIndexingJob
from app.jobs.email_contacts import UpdateContactInteractionsJob
from app.models.accounts import User
from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.contact import EmailContact
from config import logger
from config.enums import (
    AuthenticationProvider,
    ContactsSyncStatus,
    JobQueue,
)
from config.logging import LoggingContext
from infra.jobs import JobDefinition, enqueue_job
from integrations.google.gmail import (
    GoogleAPIClientBase,
    get_google_api_client,
)
from integrations.google.helpers import gmail_oauth_error_handling
from integrations.google.models import GmailAccount
from integrations.google.oauth import (
    GOOGLE_GMAIL_SCOPES,
    GoogleOAuthReauthorizationRequiredError,
)
from integrations.google.types import PeoplePerson

CONTACT_SYNC_PAGE_SIZE = 1000


class SyncGmailContactsJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    user_id: UUID

    async def perform(self):
        with LoggingContext(user_id=self.user_id):
            user = (
                await User.get_or_none(id=self.user_id).select_related("organization").prefetch_related("oauth_tokens")
            )
            google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE) if user else None
            if not user or not google_token or not google_token.has_scopes(GOOGLE_GMAIL_SCOPES):
                return

            gmail_account = await GmailAccount.get_or_none(user=user)
            if not gmail_account:
                return

            async with gmail_oauth_error_handling(user):
                try:
                    google = await get_google_api_client(user, gmail_account)

                    contacts_processed = 0

                    contacts_processed += await self._sync_connections(google, gmail_account, user)
                    contacts_processed += await self._sync_other_contacts(google, gmail_account, user)

                    gmail_account.contacts_last_synced_at = datetime.now(UTC)
                    gmail_account.contacts_sync_status = ContactsSyncStatus.SUCCESS
                    await gmail_account.save(update_fields=["contacts_last_synced_at", "contacts_sync_status"])

                    await enqueue_job(UpdateContactInteractionsJob(user_id=user.id))
                except GoogleOAuthReauthorizationRequiredError:
                    # Expected: the user revoked or expired their Google grant. gmail_oauth_error_handling
                    # marks the account for reauth and logs a warning, so don't logger.exception here —
                    # that would report an expected condition to Sentry as an error.
                    logger.warning("Gmail contacts sync needs reauth")
                    gmail_account.contacts_sync_status = ContactsSyncStatus.ERROR
                    await gmail_account.save(update_fields=["contacts_sync_status"])
                    raise
                except Exception:
                    logger.exception("Failed to sync Gmail contacts for user")
                    gmail_account.contacts_sync_status = ContactsSyncStatus.ERROR
                    await gmail_account.save(update_fields=["contacts_sync_status"])
                    raise

    async def _sync_connections(self, google: GoogleAPIClientBase, gmail_account: GmailAccount, user: User) -> int:
        page_token = None
        contacts_processed = 0

        while True:
            try:
                response = await google.list_connections(
                    page_size=CONTACT_SYNC_PAGE_SIZE,
                    person_fields="names,emailAddresses,photos",
                    page_token=page_token,
                    sync_token=gmail_account.contacts_sync_token,
                    request_sync_token=gmail_account.contacts_sync_token is None,
                )
            except HttpError as e:
                if e.resp.status == status.HTTP_400_BAD_REQUEST and "EXPIRED_SYNC_TOKEN" in str(e):
                    logger.info(f"Connections sync token expired for user {user.id}, performing full sync")
                    gmail_account.contacts_sync_token = None
                    await gmail_account.save(update_fields=["contacts_sync_token"])
                    response = await google.list_connections(
                        page_size=CONTACT_SYNC_PAGE_SIZE,
                        person_fields="names,emailAddresses,photos",
                        page_token=page_token,
                        request_sync_token=True,
                    )
                elif e.resp.status == status.HTTP_429_TOO_MANY_REQUESTS:
                    logger.warning(f"Rate limit exceeded for connections sync for user {user.id}")
                    gmail_account.contacts_sync_status = ContactsSyncStatus.RATE_LIMITED
                    await gmail_account.save(update_fields=["contacts_sync_status"])
                    raise
                elif e.resp.status == status.HTTP_403_FORBIDDEN:
                    gmail_account.contacts_sync_status = ContactsSyncStatus.INSUFFICIENT_PERMISSIONS
                    await gmail_account.save(update_fields=["contacts_sync_status"])
                    raise
                else:
                    raise

            if not response:
                logger.warning(f"No response from Google People API for user {user.id}")
                return contacts_processed

            contacts = response.get("connections", [])

            for contact in contacts:
                try:
                    await self._process_contact(contact, user)
                    contacts_processed += 1
                except Exception as e:
                    resource_name = contact.get("resourceName", "unknown")
                    logger.warning(f"Failed to process connection contact {resource_name} for user {user.id}: {e}")

            # Update sync token
            if "nextSyncToken" in response:
                gmail_account.contacts_sync_token = response["nextSyncToken"]
                await gmail_account.save(update_fields=["contacts_sync_token"])

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return contacts_processed

    async def _sync_other_contacts(self, google: GoogleAPIClientBase, gmail_account: GmailAccount, user: User) -> int:
        page_token = None
        contacts_processed = 0

        while True:
            try:
                response = await google.list_other_contacts(
                    page_size=CONTACT_SYNC_PAGE_SIZE,
                    read_mask="names,emailAddresses,photos",
                    page_token=page_token,
                    sync_token=gmail_account.other_contacts_sync_token,
                    request_sync_token=gmail_account.other_contacts_sync_token is None,
                )
            except HttpError as e:
                if e.resp.status == status.HTTP_400_BAD_REQUEST and "EXPIRED_SYNC_TOKEN" in str(e):
                    logger.info(f"Other contacts sync token expired for user {user.id}, performing full sync")
                    gmail_account.other_contacts_sync_token = None
                    await gmail_account.save(update_fields=["other_contacts_sync_token"])
                    response = await google.list_other_contacts(
                        page_size=CONTACT_SYNC_PAGE_SIZE,
                        read_mask="names,emailAddresses,photos",
                        page_token=page_token,
                        request_sync_token=True,
                    )
                elif e.resp.status == status.HTTP_429_TOO_MANY_REQUESTS:
                    logger.warning(f"Rate limit exceeded for other contacts sync for user {user.id}")
                    gmail_account.contacts_sync_status = ContactsSyncStatus.RATE_LIMITED
                    await gmail_account.save(update_fields=["contacts_sync_status"])
                    raise
                elif e.resp.status == status.HTTP_403_FORBIDDEN:
                    gmail_account.contacts_sync_status = ContactsSyncStatus.INSUFFICIENT_PERMISSIONS
                    await gmail_account.save(update_fields=["contacts_sync_status"])
                    raise
                else:
                    raise

            if not response:
                logger.warning(f"No response from Google People API for user {user.id}")
                return contacts_processed

            contacts = response.get("otherContacts", [])

            for contact in contacts:
                try:
                    await self._process_contact(contact, user)
                    contacts_processed += 1
                except Exception as e:
                    resource_name = contact.get("resourceName", "unknown")
                    logger.warning(f"Failed to process other contact {resource_name} for user {user.id}: {e}")

            # Update sync token
            if "nextSyncToken" in response:
                gmail_account.other_contacts_sync_token = response["nextSyncToken"]
                await gmail_account.save(update_fields=["other_contacts_sync_token"])

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return contacts_processed

    async def _process_contact(self, contact: PeoplePerson, user: User):
        email_addresses = contact.get("emailAddresses", [])
        names = contact.get("names", [])
        photos = contact.get("photos", [])

        if not email_addresses:
            return

        for email_data in email_addresses:
            email = email_data.get("value")
            if not email:
                continue

            if not EmailAddress.is_valid_email(email):
                continue

            name = None
            if names:
                name = names[0].get("displayName")

            photo_url = None
            if photos:
                photo_url = photos[0].get("url")

            existing_contact = await EmailContact.get_or_none(email=email, user=user)

            if existing_contact:
                existing_contact.name = name
                existing_contact.photo_url = photo_url
                existing_contact.external_contact_id = contact.get("resourceName")

                if existing_contact.changes:
                    existing_contact.last_synced_at = datetime.now(UTC)
                    await existing_contact.save(update_fields=existing_contact.changes.keys())
                    await enqueue_job(ContentIndexingJob.from_model(user.organization_id, existing_contact))
            else:
                email_contact = await EmailContact.create(
                    email=email,
                    name=name,
                    photo_url=photo_url,
                    external_contact_id=contact.get("resourceName"),
                    last_synced_at=datetime.now(UTC),
                    user=user,
                    organization_id=user.organization_id,
                )
                await enqueue_job(ContentIndexingJob.from_model(user.organization_id, email_contact))


class RefreshGmailContactsJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    is_recurring = True
    retry_count = 0

    async def perform(self):
        gmail_accounts = await GmailAccount.filter(GmailAccount.filters.contacts_sync_needed()).prefetch_related(
            "user__oauth_tokens"
        )

        for gmail_account in gmail_accounts:
            google_token = gmail_account.user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
            if google_token and google_token.has_scopes(GOOGLE_GMAIL_SCOPES):
                try:
                    await SyncGmailContactsJob(user_id=gmail_account.user_id).perform()
                except Exception as e:
                    logger.exception(f"Failed to sync Gmail contacts for account {gmail_account.id}: {e}")


class UpdateAllContactInteractionsJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    is_recurring = True
    retry_count = 0

    async def perform(self):
        gmail_accounts = await GmailAccount.filter(GmailAccount.filters.has_valid_gmail_oauth()).prefetch_related(
            "user__oauth_tokens"
        )

        for gmail_account in gmail_accounts:
            google_token = gmail_account.user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
            if google_token and google_token.has_scopes(GOOGLE_GMAIL_SCOPES):
                try:
                    await enqueue_job(UpdateContactInteractionsJob(user_id=gmail_account.user_id, window_hours=4))
                except Exception:
                    logger.exception(f"Failed to enqueue contact interactions update for user {gmail_account.user_id}")
