from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.helpers.users import user_avatar_url
from app.models.accounts import Group, Organization, User


class OrganizationMCPPresenter(BaseModel):
    model_config = ConfigDict(title="Organization")

    id: str = Field(description="Unique ID")
    name: str | None = Field(description="Organization name")
    domain: str | None = Field(description="Organization domain")

    @classmethod
    def from_organization(cls, org: Organization) -> "OrganizationMCPPresenter":
        return cls(
            id=str(org.id),
            name=org.name,
            domain=org.domain,
        )


class GroupMCPPresenter(BaseModel):
    model_config = ConfigDict(title="Group")

    id: str = Field(description="Unique ID")
    name: str = Field(description="Group name")

    @classmethod
    def from_group(cls, group: Group) -> "GroupMCPPresenter":
        return cls(
            id=str(group.id),
            name=group.name,
        )

    @classmethod
    def from_groups(cls, groups: list[Group]) -> list["GroupMCPPresenter"]:
        return [cls.from_group(g) for g in groups]


class UserMCPPresenter(BaseModel):
    model_config = ConfigDict(title="User")

    id: str = Field(description="Unique ID")
    email: str = Field(description="Email address")
    name: str | None = Field(description="Display name")
    picture: str | None = Field(description="Profile picture URL")
    is_admin: bool = Field(description="Whether user is an admin")
    created_at: datetime = Field(description="When the user was created")
    organization: OrganizationMCPPresenter = Field(description="User's organization")
    groups: list[GroupMCPPresenter] = Field(description="Groups the user is a member of")

    @classmethod
    def from_user(cls, user: User) -> "UserMCPPresenter":
        groups = [m.group for m in user.group_memberships]

        return cls(
            id=str(user.id),
            email=user.email,
            name=user.name,
            picture=user_avatar_url(user),
            is_admin=user.is_admin,
            created_at=user.created_at,
            organization=OrganizationMCPPresenter.from_organization(user.organization),
            groups=GroupMCPPresenter.from_groups(groups),
        )
