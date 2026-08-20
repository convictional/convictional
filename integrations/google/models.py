from datetime import UTC, datetime, timedelta
from typing import Annotated, ClassVar
from uuid import UUID

from tortoise import BaseDBAsyncClient, fields
from tortoise.expressions import Q

from app.models.accounts import OAuthToken, User
from config.enums import AuthenticationProvider, ContactsSyncStatus, Integration
from infra.db import PartialIndex, RecordModel, transaction
from integrations.google.constants import (
    GMAIL_ACCOUNT_HISTORY_SYNC_LOCK_DEFAULT_STALE_SECONDS,
    GMAIL_WATCH_LIVENESS_THRESHOLD_SECONDS,
)
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES


class GmailAccountFilters:
    onboarding_mailbox_sync_completed: ClassVar[Q] = Q(onboarding_mailbox_sync_completed_at__isnull=False)

    @classmethod
    def expiring_soon(cls, days: int = 1):
        return Q(watch_expires_at__lt=datetime.now(UTC) + timedelta(days=days))

    @classmethod
    def contacts_sync_needed(cls):
        return (
            Q(contacts_last_synced_at__isnull=True)
            | Q(contacts_last_synced_at__lt=datetime.now(UTC) - timedelta(hours=2))
        ) & cls.has_valid_gmail_oauth()

    @classmethod
    def has_valid_gmail_oauth(cls):
        """Filter for Gmail accounts whose Google token has the Gmail scopes and a refresh token,
        and which do not require re-authorization — matching GmailAccount._has_usable_oauth so the
        jobs that use this filter don't pick up scoped-but-unrefreshable accounts."""
        clauses = []
        for scope in GOOGLE_GMAIL_SCOPES:
            clauses.append(Q(user__oauth_tokens__scope__contains=scope))
        return (
            Q(*clauses)
            & Q(user__oauth_tokens__isnull=False)
            & Q(user__oauth_tokens__refresh_token__isnull=False)
            & Q(last_auth_errored_at__isnull=True)
        )

    @classmethod
    def by_user(cls, user_id: UUID) -> Q:
        return Q(user_id=user_id)

    @classmethod
    def lock_available(cls) -> Q:
        """Filter for accounts where the history sync lock is available (either not held or stale)."""
        stale_threshold = datetime.now(UTC) - timedelta(seconds=GMAIL_ACCOUNT_HISTORY_SYNC_LOCK_DEFAULT_STALE_SECONDS)
        return Q(history_sync_locked_at__isnull=True) | Q(history_sync_locked_at__lt=stale_threshold)


class GmailAccount(RecordModel):
    email = fields.TextField()
    # Resume cursor for list_history: the max history record we've actually processed. It intentionally
    # trails the mailbox's live historyId so a record that lags in below the live pointer is re-scanned.
    history_id = fields.TextField()
    # The highest live historyId we've confirmed we've fully scanned through (including empty scans).
    # The health check compares against this — not history_id — so it stops re-triggering once caught up.
    synced_history_id: str | None = fields.TextField(null=True)
    last_sync_at: datetime | None = fields.DatetimeField(null=True)
    watch_expires_at: datetime | None = fields.DatetimeField(null=True)
    # When we last received a real-time push for this mailbox. The only proof the watch is
    # actually delivering — used by the health check to detect a silently-dead watch.
    last_push_received_at: datetime | None = fields.DatetimeField(null=True)
    last_auth_error: str | None = fields.TextField(null=True)
    last_auth_errored_at: datetime | None = fields.DatetimeField(null=True)
    contacts_sync_token: str | None = fields.TextField(null=True)
    other_contacts_sync_token: str | None = fields.TextField(null=True)
    contacts_last_synced_at: datetime | None = fields.DatetimeField(null=True)
    contacts_sync_status: ContactsSyncStatus | None = fields.CharEnumField(ContactsSyncStatus, null=True)
    onboarding_mailbox_sync_started_at: datetime | None = fields.DatetimeField(null=True)
    onboarding_mailbox_sync_completed_at: datetime | None = fields.DatetimeField(null=True)
    history_sync_locked_at: datetime | None = fields.DatetimeField(null=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User")
    user_id: Annotated[UUID, "foreign key to user"]
    filters = GmailAccountFilters()

    class Meta:
        unique_together = (("user_id", "email"),)
        indexes = [
            PartialIndex(fields=["history_sync_locked_at"], extra="history_sync_locked_at IS NOT NULL"),
        ]

    @property
    def is_onboarding_mailbox_sync_in_progress(self) -> bool:
        return (
            self.onboarding_mailbox_sync_started_at is not None and self.onboarding_mailbox_sync_completed_at is None
        )

    @property
    def has_auth_error(self) -> bool:
        return self.last_auth_errored_at is not None

    @classmethod
    async def get_authed_for_user(cls, user_id: UUID) -> "GmailAccount | None":
        """
        Get Gmail account for user if it exists and has valid OAuth scopes.
        Returns None if account doesn't exist or lacks required OAuth permissions.
        """
        gmail_account = await cls.get_or_none(user_id=user_id).prefetch_related("user__oauth_tokens")
        if not gmail_account:
            return None
        google_token = gmail_account.user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
        if not cls._has_usable_oauth(google_token):
            return None
        return gmail_account

    @classmethod
    async def get_authed_by_id(cls, gmail_account_id: UUID) -> "GmailAccount | None":
        """
        Get Gmail account by ID if it exists and has valid OAuth scopes.
        Returns None if account doesn't exist or lacks required OAuth permissions.
        """
        gmail_account = await cls.get_or_none(id=gmail_account_id).prefetch_related("user__oauth_tokens")
        if not gmail_account:
            return None
        google_token = gmail_account.user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
        if not cls._has_usable_oauth(google_token):
            return None
        return gmail_account

    @classmethod
    async def disconnect(cls, user: User) -> None:
        """Fully disconnect Gmail for a user: strip the Gmail OAuth scopes, delete the
        user's GmailAccount rows, and drop the GMAIL integration. Idempotent — safe to
        call when nothing is connected. Shared by the HTML disconnect route and the
        JSON API DELETE so the two surfaces can't diverge."""
        async with transaction() as connection:
            google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
            if google_token:
                await google_token.remove_scopes(GOOGLE_GMAIL_SCOPES, using_db=connection)
            await cls.filter(user_id=user.id).using_db(connection).delete()
            await user.remove_integration(Integration.GMAIL, using_db=connection)

    @staticmethod
    def _has_usable_oauth(google_token: OAuthToken | None) -> bool:
        # A refresh token is required, not just the scopes: a scoped token with no refresh token
        # (e.g. Gmail scopes carried onto a plain login via include_granted_scopes) can never be
        # refreshed, so treating it as connected only produces failing sync jobs.
        return bool(google_token and google_token.has_scopes(GOOGLE_GMAIL_SCOPES) and google_token.refresh_token)

    async def mark_as_requires_reauth(self, exception: Exception, using_db: BaseDBAsyncClient | None = None):
        self.last_auth_error = str(exception)
        self.last_auth_errored_at = datetime.now(UTC)
        await self.save(update_fields=["last_auth_error", "last_auth_errored_at"], using_db=using_db)

    def clear_auth_error(self):
        self.last_auth_error = None
        self.last_auth_errored_at = None

    async def mark_synced(self, history_id: str, synced_history_id: str | None = None):
        self.history_id = history_id
        if synced_history_id is not None and self.is_synced_history_newer(synced_history_id):
            self.synced_history_id = synced_history_id
        self.last_sync_at = datetime.now(UTC)
        self.clear_auth_error()
        await self.save(update_fields=self.changes.keys())

    async def mark_push_received(self):
        now = datetime.now(UTC)
        # Pushes arrive many times an hour, but liveness only needs ~1h precision (see
        # is_push_stale). Skip the write when the timestamp is already recent to avoid a
        # gmailaccount UPDATE per push.
        if self.last_push_received_at is not None and now - self.last_push_received_at < timedelta(minutes=5):
            return
        self.last_push_received_at = now
        await self.save(update_fields=["last_push_received_at"])

    def is_push_stale(self) -> bool:
        """Whether we've gone too long without a real-time push. Combined with
        is_health_check_behind, this distinguishes a silently-dead watch (undelivered mail
        AND no recent push) from a one-off dropped push on an otherwise-healthy watch."""
        if self.last_push_received_at is None:
            return True
        return self.last_push_received_at < datetime.now(UTC) - timedelta(
            seconds=GMAIL_WATCH_LIVENESS_THRESHOLD_SECONDS
        )

    async def mark_watch_expired(self):
        """Treat the watch as expired so RenewGmailWatchesJob re-establishes it on its next run."""
        self.watch_expires_at = datetime.now(UTC)
        await self.save(update_fields=["watch_expires_at"])

    async def start_onboarding_mailbox_sync(self, using_db: BaseDBAsyncClient | None = None):
        self.onboarding_mailbox_sync_started_at = datetime.now(UTC)
        await self.save(update_fields=["onboarding_mailbox_sync_started_at"], using_db=using_db)

    async def complete_onboarding_mailbox_sync(self, using_db: BaseDBAsyncClient | None = None):
        self.onboarding_mailbox_sync_completed_at = datetime.now(UTC)
        await self.save(update_fields=["onboarding_mailbox_sync_completed_at"], using_db=using_db)

    async def acquire_history_sync_lock(self) -> bool:
        """Try to acquire the history sync lock.
        Returns True if lock acquired, False if already locked."""

        now = datetime.now(UTC)

        updated = (
            await GmailAccount.filter(id=self.id)
            .filter(GmailAccountFilters.lock_available())
            .update(history_sync_locked_at=now)
        )

        if updated > 0:
            self.history_sync_locked_at = now
            return True

        return False

    async def release_history_sync_lock(self):
        """Release the history sync lock."""
        self.history_sync_locked_at = None
        await self.save(update_fields=["history_sync_locked_at"])

    def is_history_newer(self, other_history_id: str) -> bool:
        return int(other_history_id) > int(self.history_id)

    def is_synced_history_newer(self, other_history_id: str) -> bool:
        return self.synced_history_id is None or int(other_history_id) > int(self.synced_history_id)

    def is_health_check_behind(self, live_history_id: str) -> bool:
        """Whether the live mailbox historyId has moved past everything we've confirmed we've scanned.

        Compares against synced_history_id (the caught-up marker), falling back to the resume cursor
        when the marker is unset (pre-backfill, or fresh out of onboarding). Using the marker — which
        advances even on empty scans — is what stops the health check from re-triggering forever on the
        normal gap between the live historyId and the trailing resume cursor.
        """
        baseline = self.synced_history_id or self.history_id
        return int(live_history_id) > int(baseline)

    def is_history_older_or_equal(self, other_history_id: str) -> bool:
        return int(other_history_id) <= int(self.history_id)

    def is_history_older(self, other_history_id: str) -> bool:
        return int(other_history_id) < int(self.history_id)
