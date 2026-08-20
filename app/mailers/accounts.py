from dataclasses import dataclass

from app.models.accounts import Organization, User
from app.models.workspaces.email.address import EmailAddress
from config import settings
from infra.email import EmailMessage, Mailer


@dataclass
class NewOrganizationMailer(Mailer):
    organization: Organization

    async def send(self):
        if not settings.signup_email:
            return None

        message = self.new_organization_email(self.organization)
        return await self.deliver(message)

    def new_organization_email(self, organization: Organization) -> EmailMessage:
        message = EmailMessage(to=settings.signup_email)
        return self.render(message, "new_organization.jinja", organization=organization)


@dataclass
class NewUserMailer(Mailer):
    user: User

    async def send(self):
        if not settings.new_user_notification_emails:
            return None

        message = self.new_user_email(self.user)
        return await self.deliver(message)

    def new_user_email(self, user: User) -> EmailMessage:
        recipients = EmailAddress.parse_list_addresses(settings.new_user_notification_emails)
        message = EmailMessage(to=", ".join(recipients))
        return self.render(
            message,
            "new_user.jinja",
            user_id=str(user.id),
            email=user.email,
            name=user.display_name,
            bio=user.bio or "",
            created_at=user.created_at.isoformat(),
            organization_id=str(user.organization.id),
            invited_by_id=str(user.invited_by.id) if user.invited_by else "",
        )
