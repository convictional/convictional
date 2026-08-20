import re
from dataclasses import dataclass

from jinja2 import TemplateNotFound

from app.models.accounts import User
from app.models.collaboration.workspace import MENTION_PATTERN, Event, Mention, WorkspaceMixin
from config import logger
from config.enums import EventAction
from infra.email import EmailHeaders, EmailMessage, Mailer


def render_mention_markers(text: str, emphasized_name: str) -> str:
    """Turn raw `@[Name]` markers into readable `@Name`, bolding the recipient's own.

    The mention email renders content as markdown, so the raw bracket syntax
    would otherwise show through; bolding `emphasized_name` puts the reader's eye
    on why they were pinged. Applied at render time, not in storage, so other
    channels (push strips markers to a plain name) stay unaffected.
    """

    def render(match: re.Match[str]) -> str:
        name = match.group(1)
        return f"**@{name}**" if name == emphasized_name else f"@{name}"

    return re.sub(MENTION_PATTERN, render, text)


@dataclass
class EventMailer(Mailer):
    event: Event
    user: User

    async def send(self):
        resource = await self.event.workspace.fetch_resource_or_none()
        if not resource or resource.is_deleted:
            return

        if not self.user.has_logged_in:
            logger.info(f"User {self.user.id} has not logged in, skipping EventMailer email.")
            return

        message = self.event_email(self.event, self.user, resource, **(await self._context_for(self.event, self.user)))
        return await self.deliver(message)

    async def _context_for(self, event: Event, user: User):
        if event.action == EventAction.MEETING_AGENDA_UPDATED:
            editors = []
            if event.details.get("editor_ids"):
                editors = await User.filter(id__in=event.details["editor_ids"])
            return {"editors": editors}

        return {}

    def event_email(self, event: Event, user: User, resource: WorkspaceMixin, **context) -> EmailMessage:
        message = EmailMessage(
            to=user.email,
            headers=EmailHeaders([{"name": "X-Convictional-GID", "value": resource.global_id.to_param}]),
        )
        if not event.is_system and event.creator:
            message.display_from = event.creator.display_name

        try:
            return self.render(message, f"events/{event.action.value}.jinja", event=event, user=user, **context)
        except TemplateNotFound:
            return self.render(message, "events/default.jinja", event=event, user=user, **context)


@dataclass
class MentionMailer(Mailer):
    mention: Mention

    async def send(self):
        await self.mention.workspace.fetch_resource_or_none()
        if not self.mention.workspace.resource or self.mention.workspace.resource.is_deleted:
            return

        if not self.mention.mentioned.has_logged_in:
            logger.info(f"User {self.mention.mentioned.id} has not logged in, skipping MentionMailer email.")
            return

        message = self.mention_email(self.mention)
        return await self.deliver(message)

    def mention_email(self, mention: Mention) -> EmailMessage:
        message = EmailMessage(to=mention.mentioned.email, display_from=mention.creator.display_name)
        body = render_mention_markers(mention.content, mention.mentioned.display_name)
        return self.render(message, "mention.jinja", mention=mention, body=body)
