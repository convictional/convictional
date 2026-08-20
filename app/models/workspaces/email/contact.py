from datetime import datetime
from typing import Annotated
from uuid import UUID

from tortoise import fields
from tortoise.expressions import Q

from app.models.accounts import Organization, User
from app.models.workspaces.email.address import EmailAddress
from infra.db import GinIndex, RecordModel


class EmailContactFilters:
    @staticmethod
    def search(search_term: str, user_id: UUID) -> Q:
        return Q(Q(name__icontains=search_term) | Q(email__icontains=search_term)) & Q(user_id=user_id)

    @staticmethod
    def by_user(user_id: UUID) -> Q:
        return Q(user_id=user_id)

    @staticmethod
    def by_organization(organization_id: UUID) -> Q:
        return Q(organization_id=organization_id)

    @staticmethod
    def by_emails(emails: list[str]) -> Q:
        return Q(email__in=emails)


class EmailContact(RecordModel):
    external_contact_id: str | None = fields.TextField(null=True)
    email = fields.TextField()
    name: str | None = fields.TextField(null=True)
    photo_url: str | None = fields.TextField(null=True)
    last_synced_at: datetime | None = fields.DatetimeField(null=True)
    last_interacted_at: datetime | None = fields.DatetimeField(null=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User", related_name="email_contacts")
    user_id: Annotated[UUID, "foreign key to user"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField("convictional.Organization")
    organization_id: Annotated[UUID, "foreign key to organization"]
    filters = EmailContactFilters()

    class Meta:
        unique_together = [("email", "user_id")]
        indexes = [
            ("email",),
            ("user_id",),
            ("user_id", "name", "email"),
            ("user_id", "last_interacted_at"),
            GinIndex(fields=("name",), name="idx_emailcontact_name_gin", opclass="gin_trgm_ops"),
            GinIndex(fields=("email",), name="idx_emailcontact_email_gin", opclass="gin_trgm_ops"),
        ]

    def __str__(self) -> str:
        return EmailAddress.parse(self.email).display_name
