from uuid import UUID

from app.mailers.accounts import NewOrganizationMailer, NewUserMailer
from app.mailers.collaboration import UserInvitedMailer
from app.mailers.feedback import FeedbackMailer
from app.mailers.onboarding import OnboardingMailboxSyncCompletedMailer
from app.mailers.research import ResearchQuestionMailer
from app.models.accounts import Organization, User
from app.models.commands import ResearchQuestion
from config.enums import JobQueue
from infra.jobs import JobDefinition


class UserInvitedEmailJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    user_id: UUID
    note: str

    async def perform(self):
        user = await User.get(id=self.user_id).prefetch_related("organization", "invited_by")

        await UserInvitedMailer(user, self.note).send()


class SendNewOrganizationEmailJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    organization_id: UUID

    async def perform(self):
        organization = await Organization.get(id=self.organization_id).prefetch_related("users")

        await NewOrganizationMailer(organization).send()


class SendNewUserEmailJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    user_id: UUID

    async def perform(self):
        user = await User.get_or_none(id=self.user_id).prefetch_related("organization", "invited_by")
        if not user:
            return

        await NewUserMailer(user).send()


class SendFeedbackEmailJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    url: str
    description: str
    user_email: str
    attachment_ids: list[UUID] = []
    sentry_event_id: str | None = None

    async def perform(self):
        await FeedbackMailer(
            url=self.url,
            description=self.description,
            user_email=self.user_email,
            attachment_ids=self.attachment_ids,
            sentry_event_id=self.sentry_event_id,
        ).send()


class SendResearchQuestionEmailJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    research_question_id: UUID

    async def perform(self):
        question = await ResearchQuestion.get_or_none(id=self.research_question_id).prefetch_related(
            "creator", "research__iterations__queries"
        )
        if not question:
            return

        if not question.is_response_complete:
            return

        # response_message_id is set only after a successful send — bail if a retry or duplicate
        # enqueue already delivered.
        if question.response_message_id:
            return

        response_message_id = await ResearchQuestionMailer(question).send()
        if response_message_id:
            question.response_message_id = response_message_id
            await question.save(update_fields=["response_message_id"])


class SendOnboardingMailboxSyncCompletedEmailJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    user_id: UUID

    async def perform(self):
        user = await User.get(id=self.user_id).prefetch_related("organization")
        await OnboardingMailboxSyncCompletedMailer(user).send()
