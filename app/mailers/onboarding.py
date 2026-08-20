from dataclasses import dataclass

from app.models.accounts import User
from config.enums import Integration
from infra.email import EmailMessage, Mailer


@dataclass
class OnboardingMailboxSyncCompletedMailer(Mailer):
    user: User

    async def send(self):
        message = self.onboarding_mailbox_sync_completed_email(self.user)
        return await self.deliver(message)

    def onboarding_mailbox_sync_completed_email(self, user: User) -> EmailMessage:
        message = EmailMessage(to=user.email)
        return self.render(
            message,
            "onboarding_mailbox_sync_completed.jinja",
            user=user,
            is_calendar_connected=user.is_integrated_with(Integration.RECALL_AI_CALENDAR),
        )
