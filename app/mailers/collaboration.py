from dataclasses import dataclass

from app.models.accounts import User
from infra.email import EmailMessage, Mailer


@dataclass
class UserInvitedMailer(Mailer):
    user: User
    note: str

    async def send(self):
        message = self.user_invited_email(self.user, self.note)
        return await self.deliver(message)

    def user_invited_email(self, user: User, note: str) -> EmailMessage:
        message = EmailMessage(to=user.email)
        return self.render(message, "user_invited.jinja", user=user, note=note)
