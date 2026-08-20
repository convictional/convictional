import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Annotated, ClassVar, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from tortoise import BaseDBAsyncClient, fields
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from tortoise.manager import Manager
from tortoise.query_utils import Prefetch
from tortoise.signals import post_save

from config import logger
from config.enums import (
    AuthenticationProvider,
    Integration,
    PushProtocol,
    SignupReason,
    UpdateFrequency,
)
from config.settings import settings
from infra.db import (
    JSONField,
    LocalTimeField,
    NonDeletedManager,
    RecordModel,
    SoftDeleteableFilters,
    SoftDeleteableMixin,
    after_commit,
    allow_soft_deleted,
    transaction,
)
from infra.llm import LLM
from infra.messaging import Topic
from infra.oauth import IDToken, Token
from infra.storage import FileReference
from infra.vectors import Vectors
from lib.images import ImageProcessingError, to_square_webp
from lib.strings import canonicalize_email
from lib.user_agent import platform_label

PUBLIC_DOMAINS = [
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "aol.com",
    "live.com",
    "protonmail.com",
    "zoho.com",
    "gmx.com",
    "mail.com",
    "yandex.com",
    "tutanota.com",
    "fastmail.com",
    "inbox.com",
    "rocketmail.com",
    "rediffmail.com",
    "mail.ru",
]

USER_EMAIL_MAX_LENGTH = 255


# Both refusals are raised where the create decision is made (get_or_create_by_oauth) and
# turned into a response by refused_signup_handler; they live in the model layer because
# app.models must not import from app.routers.
class SignupsDisabledError(Exception):
    pass


class SignupBlockedError(Exception):
    pass


AVATAR_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
AVATAR_SIZE = 512
AVATAR_QUALITY = 85
AVATAR_OUTPUT_MIME = "image/webp"
AVATAR_OUTPUT_FILENAME = "avatar.webp"
AVATAR_ACCEPTED_INPUT_MIMES = frozenset({"image/jpeg", "image/png", "image/webp"})


def process_avatar_image(data: bytes, content_type: str | None) -> bytes:
    """Validate an uploaded avatar against our policy and re-encode it as a square WebP.

    Composes the generic `to_square_webp` primitive with this app's avatar policy
    (accepted types, size cap, dimensions). Raises ImageProcessingError if the type
    isn't allowed, the data is too large, or it can't be decoded — callers map that
    to their own HTTP status. Storage stays with the caller; this is a pure transform.
    """
    if content_type not in AVATAR_ACCEPTED_INPUT_MIMES:
        raise ImageProcessingError("Avatar must be a JPEG, PNG, or WebP image")
    if len(data) > AVATAR_MAX_UPLOAD_BYTES:
        raise ImageProcessingError(f"Avatar must be {AVATAR_MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller")
    return to_square_webp(data, size=AVATAR_SIZE, quality=AVATAR_QUALITY)


#
# Organizations
#
#


class OrganizationFilters:
    @classmethod
    def by_domain(cls, domain: str) -> Q:
        return Q(domain=domain)


class Organization(SoftDeleteableMixin, RecordModel):
    name = fields.CharField(max_length=255, null=True)
    domain = fields.CharField(max_length=255, unique=True, db_index=True, null=True)
    oidc_token = fields.CharField(max_length=255, null=True)
    system_prompt: str | None = fields.TextField(null=True)
    integrations = JSONField[list[Integration]](default=list)
    users: fields.ReverseRelation["User"]
    filters = OrganizationFilters()

    @classmethod
    def extract_private_domain_from_email(cls, email: str):
        domain = email.rsplit("@", maxsplit=1)[-1]
        return domain if domain not in PUBLIC_DOMAINS else None

    @staticmethod
    def is_domain_banned(email: str, banned_domains: list[str] | None = None) -> bool:
        if banned_domains is None:
            banned_domains = settings.banned_domains
        if not email or "@" not in email:
            return False
        domain = email.rsplit("@", maxsplit=1)[-1]
        return domain in banned_domains

    @classmethod
    async def get_or_none_by_oauth_id_token(cls, token: IDToken, using_db: BaseDBAsyncClient | None = None):
        if not token.email or not token.organization_code:
            return None
        org = await cls.get_or_none(oidc_token=token.organization_code, using_db=using_db)
        if org:
            return org

        private_domain = cls.extract_private_domain_from_email(token.email)
        if private_domain:
            org = await cls.get_or_none(domain=private_domain, using_db=using_db)
            if org and not org.oidc_token:
                return org
        return None

    @property
    def display_name(self):
        if self.name:
            return self.name

        if self.domain:
            return self.domain

        return "Unknown"

    @property
    def llm(self):
        api_key = settings.anthropic_api_key.get_secret_value()
        return LLM(api_key, organization_id=self.id)

    @property
    def vectors(self):
        return Vectors()

    @property
    def is_onboarding_complete(self):
        return self.name is not None

    async def fetch_users_by_email(self):
        users = await self.users.all()
        return {user.email: user for user in users}

    async def first_user(self):
        return await self.users.order_by("created_at").first()

    async def primary_email(self):
        user = await self.first_user()
        if not user:
            return None
        return user.email

    async def add_integration(self, integration: Integration, using_db: BaseDBAsyncClient | None = None):
        if integration not in self.integrations:
            self.integrations.append(integration)
            await self.save(update_fields=["integrations"], using_db=using_db)

    async def remove_integration(self, integration: Integration, using_db: BaseDBAsyncClient | None = None):
        if integration in self.integrations:
            integrations = self.integrations.copy()
            integrations.remove(integration)
            self.integrations = integrations
            await self.save(update_fields=["integrations"], using_db=using_db)

    def is_integrated_with(self, integration: Integration) -> bool:
        return integration in self.integrations


class UserFilters(SoftDeleteableFilters):
    has_logged_in: ClassVar[Q] = Q(last_logged_in_at__isnull=False)

    @classmethod
    def by_auth_provider(cls, provider: AuthenticationProvider) -> Q:
        return Q(oauth_tokens__provider=provider)

    @classmethod
    def by_email(cls, email: str) -> Q:
        return Q(email_aliases__address=email)

    @classmethod
    def by_any_email(cls, emails: list[str]) -> Q:
        return Q(email__in=emails) | Q(email_aliases__address__in=emails)

    @classmethod
    def by_email_exact(cls, email: str) -> Q:
        return Q(email=email)

    @classmethod
    def by_organization(cls, organization_id) -> Q:
        return Q(organization_id=organization_id)


class User(SoftDeleteableMixin, RecordModel):
    email = fields.CharField(max_length=USER_EMAIL_MAX_LENGTH, unique=True, db_index=True)
    has_verified_email = fields.BooleanField(default=False)
    name = fields.CharField(max_length=255, null=True)
    oauth_picture = fields.CharField(max_length=2048, null=True)
    last_logged_in_at = fields.DatetimeField(null=True)
    last_seen_at = fields.DatetimeField(auto_now_add=True)
    last_logout_at = fields.DatetimeField(null=True)
    bio = fields.TextField(null=True)
    signup_reason = fields.TextField(null=True)
    time_zone = fields.CharField(max_length=255, null=True)
    # Both null → push delivers at any time. Working hours are opt-in.
    push_working_hours_start: time | None = LocalTimeField(null=True)
    push_working_hours_end: time | None = LocalTimeField(null=True)
    is_admin = fields.BooleanField(default=False)
    integrations = JSONField[list[Integration]](default=list)
    onboarding_mailbox_sync_started_at: datetime | None = fields.DatetimeField(null=True)
    onboarding_mailbox_sync_completed_at: datetime | None = fields.DatetimeField(null=True)
    organization: fields.ForeignKeyRelation["Organization"] = fields.ForeignKeyField(
        "convictional.Organization", related_name="users", db_index=True
    )
    organization_id: Annotated[UUID, "foreign key to organization"]
    invited_by: fields.ForeignKeyNullableRelation["User"] = fields.ForeignKeyField(
        "convictional.User", related_name="invited_users", null=True
    )
    invited_by_id: Annotated[UUID | None, "foreign key to inviting user"]
    avatar_file: fields.ForeignKeyNullableRelation[FileReference] = fields.ForeignKeyField(
        "convictional.FileReference", related_name="user_avatars", null=True, on_delete=fields.SET_NULL
    )
    avatar_file_id: Annotated[UUID | None, "foreign key to uploaded avatar file"]
    oauth_tokens: fields.ReverseRelation["OAuthToken"]
    email_aliases: fields.ReverseRelation["EmailAlias"]
    group_memberships: fields.ReverseRelation["GroupMember"]
    push_subscriptions: fields.ReverseRelation["PushSubscription"]
    active = NonDeletedManager()  # This is just an alias for User.nondeleted
    filters = UserFilters()

    class Meta:
        ordering = ["name", "email"]
        manager = Manager()  # Override the default manager of SoftDeleteableMixin to allow including deleted users

    @classmethod
    async def get_or_create_by_oauth(cls, token: Token, banned_domains: list[str] | None = None):
        if cls.is_login_blocked(token.id_token_model):
            raise SignupBlockedError

        if banned_domains is None:
            banned_domains = settings.banned_domains

        async with transaction() as connection:
            user = await cls.get_or_none_by_id_token(token.id_token_model, using_db=connection)
            is_new_login = False
            organization_was_created = False
            user_was_created = False

            if not user:
                # Nothing has been written yet, so refusing here leaves no partial account
                # behind. Checked ahead of the blocklists because a freeze is the broader
                # condition — during one, no identity gets an account either way.
                if not settings.signups_enabled:
                    raise SignupsDisabledError

                if Organization.is_domain_banned(token.id_token_model.email, banned_domains):
                    raise SignupBlockedError

                organization = await Organization.get_or_none_by_oauth_id_token(token.id_token_model, connection)
                if not organization:
                    organization = await Organization.create(
                        oidc_token=token.id_token_model.organization_code, using_db=connection
                    )
                    organization_was_created = True

                user = await cls.create(
                    using_db=connection,
                    email=token.id_token_model.email,
                    name=token.id_token_model.name,
                    oauth_picture=token.id_token_model.picture,
                    has_verified_email=token.id_token_model.email_verified or False,
                    organization=organization,
                )
                is_new_login = True
                user_was_created = True

            await user.fetch_related("oauth_tokens", using_db=connection)
            if not user.has_logged_in:
                is_new_login = True

            if user.is_deleted:
                if Organization.is_domain_banned(user.email, banned_domains):
                    raise SignupBlockedError
                await user.restore(using_db=connection)

            if not isinstance(user.organization, Organization):
                await user.fetch_related("organization", using_db=connection)

            if user.organization and not user.organization.oidc_token and token.id_token_model.organization_code:
                user.organization.oidc_token = token.id_token_model.organization_code
                await user.organization.save(using_db=connection)

            await OAuthToken.create_or_update_by_token(user, token, using_db=connection)
            await user.fetch_related("oauth_tokens", using_db=connection)

            if user_was_created:
                organization_id = user.organization_id

                async def broadcast(using_db: BaseDBAsyncClient | None):
                    await Topic("organization_members", organization_id=organization_id).broadcast(
                        added_user_id=str(user.id)
                    )

                await after_commit(broadcast)

            return user, is_new_login, organization_was_created, user_was_created

    @classmethod
    async def get_or_none_by_id_token(cls, id_token: IDToken, using_db: BaseDBAsyncClient | None = None):
        if not id_token.email:
            return None

        # Find by existing OAuthToken
        possible_tokens = (
            await OAuthToken.filter(provider=id_token.provider, client_id=id_token.sub)
            .using_db(using_db)
            .prefetch_related("user")
        )
        if possible_tokens:
            return possible_tokens[0].user

        # Fallback to find by email
        user = await User.filter(User.filters.by_email_exact(id_token.email)).using_db(using_db).first()
        return user

    @staticmethod
    def is_login_blocked(id_token: IDToken) -> bool:
        """Whether this identity is barred from signing in, by Google subject id or canonicalized
        email. Enforced on every login (see get_or_create_by_oauth); the block is independent
        of any user row because deleting a user does not stop them logging back in and
        recreating the account. Both lists are env-backed (settings.blocked_oauth_subs /
        settings.blocked_emails) so no personal identifier is committed to source history. The
        Google `sub` is matched too because email alone is bypassable (a new address, or Gmail's
        dot/+tag aliasing)."""
        if id_token.sub in settings.blocked_oauth_subs:
            return True
        if not id_token.email:
            return False
        canonical_blocked = {canonicalize_email(email) for email in settings.blocked_emails}
        return canonicalize_email(id_token.email) in canonical_blocked

    @property
    def display_name(self):
        friendly_name = self.name or self.email

        if self.is_deleted:
            return f"{friendly_name} (deleted)"

        return friendly_name

    @property
    def split_display_name(self):
        return self.display_name.split(" ") if self.display_name else [""]

    @property
    def first_name(self):
        return self.split_display_name[0]

    @property
    def is_superuser(self):
        # settings.superuser_emails is lowercased at parse time. Granting matches the exact
        # address, unlike the blocklist above, which matches through canonicalize_email: a
        # wider match is right for refusing an identity and wrong for granting privilege.
        return self.email.lower() in settings.superuser_emails

    @property
    def oauth_authentication_token(self):
        """Returns the newest OAuth token that asserts user identity (has client_id)."""
        if not self.oauth_tokens:
            return None

        for token in self.oauth_tokens:
            if token.client_id:
                return token

        return None

    def oauth_token_for_provider(self, provider: AuthenticationProvider) -> "OAuthToken | None":
        """Returns the OAuth token for a given provider, if it exists."""
        if not self.oauth_tokens:
            return None

        for token in self.oauth_tokens:
            if token.provider == provider:
                return token

        return None

    @classmethod
    async def get_with_scopes(
        cls, user_id: UUID, required_scopes: list[str], provider: AuthenticationProvider
    ) -> "User | None":
        """
        Get user by ID if they exist and have OAuth scopes for the specified provider.
        Returns None if user doesn't exist or lacks required OAuth permissions.
        """
        user = await cls.get_or_none(id=user_id).select_related("organization").prefetch_related("oauth_tokens")
        if not user:
            return None
        token = user.oauth_token_for_provider(provider)
        if not token or not token.has_scopes(required_scopes):
            return None
        return user

    @property
    def has_logged_in(self):
        return self.oauth_authentication_token is not None

    @property
    def authentication(self):
        if self.oauth_authentication_token:
            return self.oauth_authentication_token.provider
        return AuthenticationProvider.TESTING

    @property
    def is_onboarding_mailbox_sync_complete(self):
        return self.onboarding_mailbox_sync_completed_at is not None

    async def mark_login(self):
        self.last_logged_in_at = datetime.now(UTC)
        await self.save(update_fields=["last_logged_in_at"])

    async def mark_logout(self, using_db: BaseDBAsyncClient | None = None):
        self.last_logout_at = datetime.now(UTC)
        await self.save(update_fields=["last_logout_at"], using_db=using_db)

    async def mark_seen(self):
        self.last_seen_at = datetime.now(UTC)
        await self.save(update_fields=["last_seen_at"])

    async def make_admin(self):
        self.is_admin = True
        await self.save()

    async def deactivate(self) -> bool:
        # Deactivating a member is soft-delete + forced logout + notifying the org roster, as one
        # operation. Returns False without side effects if already deactivated, so callers can't
        # re-stamp deleted_at or emit a phantom membership broadcast. Mirrors Invite, which owns
        # the add/restore side.
        if self.is_deleted:
            return False
        # The two writes share a transaction so they can't half-apply. The broadcast is registered
        # after the block (via after_commit) so it only fires once those writes have committed.
        async with transaction() as connection:
            await self.soft_delete(using_db=connection)
            await self.mark_logout(using_db=connection)
        await self._broadcast_membership_change(removed_user_id=str(self.id))
        return True

    async def reactivate(self) -> bool:
        if not self.is_deleted:
            return False
        # Single write; the broadcast fires immediately (no enclosing transaction) via after_commit.
        await self.restore()
        await self._broadcast_membership_change(added_user_id=str(self.id))
        return True

    async def _broadcast_membership_change(self, **payload: str):
        organization_id = self.organization_id

        # after_commit so the broadcast lands only once any enclosing transaction commits; it runs
        # immediately when there's no transaction. Matches how Invite broadcasts added_user_id.
        async def broadcast(using_db: BaseDBAsyncClient | None):
            await Topic("organization_members", organization_id=organization_id).broadcast(**payload)

        await after_commit(broadcast)

    def has_email(self, email: str) -> bool:
        return self.email == email or any(alias.address == email for alias in self.email_aliases)

    async def sync_email_aliases(self, email_addresses: list[str]):
        async with transaction() as connection:
            await EmailAlias.filter(user_id=self.id).using_db(connection).delete()
            all_addresses = {self.email, *email_addresses}
            for email_address in all_addresses:
                await EmailAlias.get_or_create(address=email_address, user_id=self.id, using_db=connection)

    async def add_integration(self, integration: Integration, using_db: BaseDBAsyncClient | None = None):
        if integration not in self.integrations:
            self.integrations.append(integration)
            await self.save(update_fields=["integrations"], using_db=using_db)

    async def remove_integration(self, integration: Integration, using_db: BaseDBAsyncClient | None = None):
        if integration in self.integrations:
            integrations = self.integrations.copy()
            integrations.remove(integration)
            self.integrations = integrations
            await self.save(update_fields=["integrations"], using_db=using_db)

    def is_integrated_with(self, integration: Integration) -> bool:
        return integration in self.integrations

    @classmethod
    async def organization_has_integration(cls, organization_id: UUID, integration: Integration) -> bool:
        """Whether any active member of the organization has the given integration. Used to
        decide whether an org-installed app (e.g. Slack) is available to a member who hasn't
        personally connected it. Scoped to `active` so soft-deleted members don't count."""
        # JSONB containment so the DB answers the boolean — never materialize the org's
        # users just to OR a flag (`labels__contains=[...]` is the same idiom).
        return await cls.active.filter(
            cls.filters.by_organization(organization_id),
            integrations__contains=[integration],
        ).exists()

    async def set_push_working_hours(
        self, start: time | None, end: time | None, *, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        """Set or clear the push working-hours window. Both columns must move
        together; mixed-null pairs are rejected upstream by the request schema."""
        self.push_working_hours_start = start
        self.push_working_hours_end = end
        await self.save(update_fields=["push_working_hours_start", "push_working_hours_end"], using_db=using_db)

    def is_in_working_hours(self, when: datetime) -> bool:
        """Working hours are opt-in. Both columns NULL → push delivers at any time.
        `when` is the event's wall-clock, not now(): queue lag at 6:59pm→7:01pm
        should still deliver because the user implicitly consented when the message
        was sent.
        """
        start = self.push_working_hours_start
        end = self.push_working_hours_end
        if start is None or end is None:
            return True

        # `.time()` inherits the datetime's tzinfo; strip it to compare cleanly against
        # the naive LocalTimeField columns.
        local = when.astimezone(self._zone()).time().replace(tzinfo=None)
        if start == end:
            # Degenerate window: "never push" beats the cross-midnight branch's
            # "always push" — silent over-notify is the worse failure mode.
            return False
        if start < end:
            return start <= local < end
        # Cross-midnight (e.g. 22:00–06:00 night shift).
        return local >= start or local < end

    def _zone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.time_zone or "UTC")
        except ZoneInfoNotFoundError:
            logger.warning("invalid user.time_zone %r for user %s — falling back to UTC", self.time_zone, self.id)
            return ZoneInfo("UTC")

    async def mark_onboarding_mailbox_sync_started(self, using_db: BaseDBAsyncClient | None = None):
        if self.onboarding_mailbox_sync_started_at:
            return

        now = datetime.now(UTC)
        self.onboarding_mailbox_sync_started_at = now

        await self.save(update_fields=["onboarding_mailbox_sync_started_at"], using_db=using_db)

    async def mark_onboarding_mailbox_sync_complete(self, using_db: BaseDBAsyncClient | None = None):
        if self.is_onboarding_mailbox_sync_complete:
            return

        now = datetime.now(UTC)
        if not self.onboarding_mailbox_sync_started_at:
            self.onboarding_mailbox_sync_started_at = now
        self.onboarding_mailbox_sync_completed_at = now

        await self.save(
            update_fields=["onboarding_mailbox_sync_started_at", "onboarding_mailbox_sync_completed_at"],
            using_db=using_db,
        )


@post_save(User)
async def ensure_user_primary_email_alias(
    sender: "type[User]",
    instance: User,
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    if created:
        await EmailAlias.get_or_create(address=instance.email, user_id=instance.id, using_db=using_db)


# Refresh slightly ahead of the real expiry so we never hand out a token that
# dies mid-request. Mirrors google-auth's own proactive-refresh threshold.
OAUTH_TOKEN_REFRESH_BUFFER = timedelta(minutes=5)


class OAuthToken(RecordModel):
    provider = fields.CharEnumField(AuthenticationProvider, max_length=255)
    client_id = fields.CharField(max_length=255, null=True)
    access_token = fields.TextField(description="protected_column")
    refresh_token = fields.TextField(null=True, description="protected_column")
    scope = fields.TextField()
    expires_at = fields.DatetimeField(null=True)
    is_decrypted = fields.BooleanField(default=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User", related_name="oauth_tokens")
    user_id: Annotated[UUID, "foreign key to user"]

    class Meta:
        ordering = ["-created_at"]
        indexes = (
            ("user_id", "provider", "client_id"),
            ("is_decrypted",),
        )

    @classmethod
    async def create_or_update_by_token(cls, user: User, token: Token, using_db: BaseDBAsyncClient | None = None):
        client_id = token.id_token_model.sub if token.id_token_model else None
        oauth_token = await OAuthToken.get_or_init(
            user_id=user.id, provider=token.provider, client_id=client_id, using_db=using_db
        )

        incoming_scopes = set(token.scope.split(" ")) if token.scope else set()
        existing_scopes = set(oauth_token.scopes)

        # A single row holds the durable credential per (user, provider, Google
        # `sub`), and every OAuth client for that account resolves to it — including
        # clients that only ever request a subset of the scopes (e.g. an
        # identity-only sign in). Adopting a narrower login's credential would both
        # drop the broader scopes AND store an access/refresh token that cannot
        # exercise them: a refresh token is bound to the client that minted it, so a
        # later server-side refresh (always via the web client) would be rejected.
        # Only take the incoming credential when it is at least as broad as what we
        # already hold; otherwise the login stands as authentication only and the
        # established credential is preserved.
        if existing_scopes and not incoming_scopes.issuperset(existing_scopes):
            return oauth_token

        oauth_token.access_token = token.access_token
        oauth_token.scope = token.scope
        oauth_token.expires_at = token.expires_at

        # Google only returns the refresh token on the first auth, so we only update it if it's provided
        if token.refresh_token:
            oauth_token.refresh_token = token.refresh_token

        await oauth_token.save(using_db=using_db)

        return oauth_token

    @property
    def scopes(self) -> list[str]:
        return self.scope.split(" ") if self.scope else []

    @property
    def is_expired(self) -> bool:
        # Treat an unknown expiry as expired so callers refresh rather than
        # trust a token whose freshness we can't verify.
        if self.expires_at is None:
            return True
        return datetime.now(UTC) >= self.expires_at - OAUTH_TOKEN_REFRESH_BUFFER

    @property
    def credentials_expiry(self) -> datetime | None:
        # google-auth's Credentials.expiry must be a naive UTC datetime.
        return self.expires_at.astimezone(UTC).replace(tzinfo=None) if self.expires_at else None

    def has_scopes(self, scopes: list[str]) -> bool:
        return all(scope in self.scope for scope in scopes)

    async def remove_scopes(self, scopes: list[str], using_db: BaseDBAsyncClient | None = None):
        new_scopes = [scope for scope in self.scope.split(" ") if scope not in scopes]
        self.scope = " ".join(new_scopes)
        await self.save(update_fields=["scope"], using_db=using_db)

    async def refresh(
        self, access_token: str, refresh_token: str, expires_at: datetime, using_db: BaseDBAsyncClient | None = None
    ):
        if not refresh_token:
            raise ValueError("Refresh token cannot be None when updating OAuth token")
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        await self.save(update_fields=["access_token", "refresh_token", "expires_at"], using_db=using_db)


class PushSubscriptionLimitError(Exception):
    """Raised when a user has hit the active-subscriptions cap."""

    def __init__(self, limit: int):
        super().__init__(f"User has reached the push-subscription cap of {limit}.")
        self.limit = limit


class PushSubscriptionUserCollisionError(Exception):
    """Raised when two distinct users race a register call against the same endpoint.

    Vanishingly rare (one browser → one push relay endpoint) but possible in
    the racing window between the dedupe SELECT and INSERT.
    """


class PushSubscription(SoftDeleteableMixin, RecordModel):
    endpoint = fields.TextField()
    protocol = fields.CharEnumField(PushProtocol, default=PushProtocol.WEB_PUSH, max_length=16)
    # Web-push only; APNs encrypts on the relay side.
    p256dh_key: str | None = fields.TextField(null=True)
    auth_key: str | None = fields.TextField(null=True, description="protected_column")
    user_agent: str | None = fields.TextField(null=True)
    platform: str | None = fields.TextField(null=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "convictional.User", related_name="push_subscriptions", on_delete=fields.CASCADE
    )
    user_id: Annotated[UUID, "foreign key to user"]

    # Far above any legitimate use (a heavy multi-device user has maybe 5
    # active subscriptions) but enough headroom to blunt a misbehaving tab
    # that calls subscribe() in a loop. Soft-deleted rows do not count.
    MAX_ACTIVE_PER_USER: ClassVar[int] = 20

    class Meta:
        ordering = ["-created_at"]
        indexes = (("user_id",),)

    @classmethod
    async def user_has_any(cls, user_id: UUID) -> bool:
        return await cls.filter(user_id=user_id).exists()

    @classmethod
    async def user_ids_with_subscriptions(
        cls, user_ids: list[UUID], *, using_db: BaseDBAsyncClient | None = None
    ) -> set[UUID]:
        """Bulk equivalent of user_has_any: the subset of `user_ids` that have at
        least one active push subscription. set() collapses duplicates from users
        with multiple devices."""
        if not user_ids:
            return set()
        return set(
            cast(
                list[UUID],
                await cls.filter(user_id__in=user_ids).using_db(using_db).values_list("user_id", flat=True),
            )
        )

    @classmethod
    async def register_for_user(
        cls,
        *,
        user_id: UUID,
        endpoint: str,
        protocol: PushProtocol = PushProtocol.WEB_PUSH,
        p256dh_key: str | None = None,
        auth_key: str | None = None,
        user_agent: str | None,
        rotated_from_endpoint: str | None = None,
    ) -> tuple["PushSubscription", bool]:
        """Register or refresh a push subscription. Returns (subscription, created).

        Same-user same-endpoint: refresh fields, restore if soft-deleted, return existing.
        Different-user same-endpoint: hard-delete the previous row, register fresh.
        Soft-deleted rotated_from row: best-effort soft-delete (used by the
        service-worker pushsubscriptionchange handler).

        APNs callers omit `p256dh_key`/`auth_key`; the request schema enforces
        the web-push pairing.

        Raises `PushSubscriptionLimitError` when the user is at the cap and
        no existing row was matched, and `PushSubscriptionUserCollisionError` if a
        concurrent insert from another user wins the race.
        """
        if rotated_from_endpoint and rotated_from_endpoint != endpoint:
            rotated_old = await cls.filter(user_id=user_id, endpoint=rotated_from_endpoint).first()
            if rotated_old and not rotated_old.is_deleted:
                await rotated_old.soft_delete()

        async with allow_soft_deleted():
            existing, active_count = await asyncio.gather(
                cls.filter(endpoint=endpoint).order_by("-created_at").first(),
                cls.filter(user_id=user_id, deleted_at__isnull=True).count(),
            )

        if existing:
            if existing.user_id == user_id:
                return await cls._refresh(existing, protocol, p256dh_key, auth_key, user_agent), False
            # Different-user collision means the device changed account; the
            # previous user no longer has access. Hard-delete so the new
            # INSERT doesn't trip the dedupe path on the very next request.
            await existing.delete()

        if active_count >= cls.MAX_ACTIVE_PER_USER:
            raise PushSubscriptionLimitError(cls.MAX_ACTIVE_PER_USER)

        try:
            subscription = await cls.create(
                user_id=user_id,
                endpoint=endpoint,
                protocol=protocol,
                p256dh_key=p256dh_key,
                auth_key=auth_key,
                user_agent=user_agent,
                platform=platform_label(user_agent),
            )
            return subscription, True
        except IntegrityError:
            # Concurrent register call inserted a row for the same endpoint
            # between our SELECT and INSERT. The partial unique index rejected
            # the second writer. Recover by treating the conflicting row as
            # the dedupe winner.
            async with allow_soft_deleted():
                existing = await cls.filter(endpoint=endpoint).order_by("-created_at").first()
            if existing and existing.user_id == user_id:
                return await cls._refresh(existing, protocol, p256dh_key, auth_key, user_agent), False
            raise PushSubscriptionUserCollisionError()

    @classmethod
    async def _refresh(
        cls,
        subscription: "PushSubscription",
        protocol: PushProtocol,
        p256dh_key: str | None,
        auth_key: str | None,
        user_agent: str | None,
    ) -> "PushSubscription":
        # Restore if soft-deleted, otherwise idempotent refresh. Single UPDATE either way.
        subscription.deleted_at = None
        subscription.protocol = protocol
        subscription.p256dh_key = p256dh_key
        subscription.auth_key = auth_key
        subscription.user_agent = user_agent
        subscription.platform = platform_label(user_agent)
        await subscription.save()
        return subscription

    @classmethod
    async def hard_delete_stale(cls, *, older_than: datetime, batch_size: int) -> int:
        """Hard-delete soft-deleted rows whose `deleted_at` predates `older_than`.

        Returns the number of rows removed. Selects in `deleted_at` order so
        repeated runs drain the queue oldest-first; caps the batch so a backlog
        can't monopolize the worker. `allow_soft_deleted` is required because
        `NonDeletedManager` hides the very rows we're targeting.
        """
        async with allow_soft_deleted():
            stale_ids = await (
                cls.filter(deleted_at__lt=older_than)
                .order_by("deleted_at")
                .limit(batch_size)
                .values_list("id", flat=True)
            )
            if not stale_ids:
                return 0
            return await cls.filter(id__in=stale_ids).delete()


class EmailAlias(RecordModel):
    address = fields.CharField(max_length=255, db_index=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User", related_name="email_aliases")
    user_id: Annotated[UUID, "foreign key to user"]

    class Meta:
        ordering = ["address"]
        indexes = (("user_id",),)
        unique_together = (("address", "user_id"),)


@dataclass
class Invite:
    inviter: User
    email: str
    using_db: BaseDBAsyncClient | None = None
    invited: User | None = None
    error: str | None = None
    banned_domains: list[str] = field(default_factory=lambda: list(settings.banned_domains))
    _is_existing_user: bool | None = field(default=None, init=False)

    @property
    def success(self) -> bool:
        return self.invited is not None and self.error is None

    @property
    def is_existing_user(self) -> bool:
        return bool(self._is_existing_user)

    async def process(self):
        if Organization.is_domain_banned(self.email, self.banned_domains):
            self.error = "This signup is banned"
            return self

        user: User | None = await User.filter(User.filters.by_email_exact(self.email)).using_db(self.using_db).first()
        self._is_existing_user = user is not None

        if user:
            if user.organization_id != self.inviter.organization_id:
                self.error = "User already belongs to another organization"
                return self
            await user.restore(using_db=self.using_db)
        else:
            user = await User.create(
                email=self.email,
                organization_id=self.inviter.organization_id,
                invited_by_id=self.inviter.id,
                signup_reason=SignupReason.INVITED.value,
                using_db=self.using_db,
            )

        async def broadcast(using_db: BaseDBAsyncClient | None):
            await Topic("organization_members", organization_id=self.inviter.organization_id).broadcast(
                added_user_id=str(user.id)
            )

        await after_commit(broadcast)

        self.invited = user
        return self


#
# Groups
#
#


class GroupFilters(SoftDeleteableFilters):
    @classmethod
    def by_organization(cls, organization_id: UUID) -> Q:
        return Q(organization_id=organization_id)

    @classmethod
    def by_member(cls, user_id: UUID) -> Q:
        return Q(members__user_id=user_id)


class Group(SoftDeleteableMixin, RecordModel):
    name: str = fields.TextField()
    organization: fields.ForeignKeyRelation["Organization"] = fields.ForeignKeyField(
        "convictional.Organization", related_name="groups"
    )
    organization_id: Annotated[UUID, "foreign key to organization"]
    members: fields.ReverseRelation["GroupMember"]
    filters = GroupFilters()

    class Meta:
        ordering = ["name"]
        indexes = (("organization_id",),)

    @staticmethod
    def active_members_prefetch() -> Prefetch:
        # deleted_at lives on User, not GroupMember, and User's default manager is
        # overridden to include soft-deleted rows — so exclude deactivated members with an
        # explicit join filter rather than a manager swap. Filtering here rather than in
        # the serializer keeps member_count and is_member consistent with the list.
        return Prefetch("members", queryset=GroupMember.filter(user__deleted_at__isnull=True).select_related("user"))

    @property
    def member_ids(self) -> set[UUID]:
        return {member.user_id for member in self.members}

    async def add_member(self, user: "User", using_db: BaseDBAsyncClient | None = None) -> "GroupMember":
        member, created = await GroupMember.get_or_create(group_id=self.id, user_id=user.id, using_db=using_db)
        if not created:
            raise ValueError("User is already a member.")
        return member

    async def remove_member(self, user: "User", using_db: BaseDBAsyncClient | None = None) -> None:
        member = await GroupMember.filter(group_id=self.id, user_id=user.id).using_db(using_db).first()
        if not member:
            raise ValueError("You are not a member.")
        await member.delete(using_db=using_db)

    def is_member(self, user_id: UUID) -> bool:
        return user_id in self.member_ids


class GroupMember(RecordModel):
    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "convictional.User", related_name="group_memberships"
    )
    user_id: Annotated[UUID, "foreign key to user"]
    group: fields.ForeignKeyRelation["Group"] = fields.ForeignKeyField("convictional.Group", related_name="members")
    group_id: Annotated[UUID, "foreign key to group"]

    class Meta:
        ordering = ["created_at"]
        indexes = (("group_id", "user_id"),)
        unique_together = (("group_id", "user_id"),)


class OrganizationUpdatesConfiguration(RecordModel):
    organization: fields.OneToOneRelation[Organization] = fields.OneToOneField(
        "convictional.Organization", related_name="updates_configuration"
    )
    organization_id: Annotated[UUID, "foreign key to organization"]

    update_schedule: str | None = fields.TextField(
        null=True, help_text="Cron format (e.g. '0 10 * * 5' for weekly on Friday at 10:00 UTC)"
    )
    frequency: UpdateFrequency = fields.CharEnumField(UpdateFrequency, default=UpdateFrequency.WEEKLY, max_length=255)
    goal_update_question: str = fields.TextField(default="How's it going?")

    @property
    def hour(self):
        if not self.update_schedule:
            return 9

        cron_parts = self.update_schedule.split()
        return int(cron_parts[1])

    @property
    def day_of_week(self):
        if not self.update_schedule:
            return "1"

        cron_parts = self.update_schedule.split()
        return cron_parts[4] if self.frequency != UpdateFrequency.MONTHLY else None

    def validate_schedule(self, frequency: UpdateFrequency, hour: int, day_of_week: str | None = None) -> str | None:
        if not (0 <= hour < 24):
            return "Hour must be between 0 and 23"

        if frequency == UpdateFrequency.WEEKLY:
            if day_of_week is None or day_of_week not in ["0", "1", "2", "3", "4", "5", "6"]:
                return "Day of week must be provided and be between 0 (Sunday) and 6 (Saturday) for weekly frequency"
        elif frequency == UpdateFrequency.MONTHLY:
            pass
        else:
            return "Invalid frequency value"

        if frequency != UpdateFrequency.MONTHLY:
            if not croniter.is_valid(self._build_cron_expression(frequency, hour, day_of_week)):
                return "Unknown schedule error"
        return None

    def set_schedule(self, frequency: UpdateFrequency, hour: int, day_of_week: str | None = None):
        self.frequency = frequency
        self.update_schedule = self._build_cron_expression(frequency, hour, day_of_week)

    def _build_cron_expression(self, frequency: UpdateFrequency, hour: int, day_of_week: str | None = None):
        if frequency == UpdateFrequency.WEEKLY:
            if day_of_week is None:
                raise ValueError("Day of week must be provided for weekly frequency")
            return f"0 {hour} * * {day_of_week}"
        elif frequency == UpdateFrequency.MONTHLY:
            return f"0 {hour} L * *"
        else:
            raise ValueError("Invalid frequency value")
