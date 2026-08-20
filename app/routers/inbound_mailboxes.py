from app.jobs.research import start_research_from_question
from app.models.accounts import User
from app.models.commands import ResearchQuestion
from app.models.workspaces.email.address import EmailAddress
from config import logger, settings
from config.enums import ResearchSource
from infra.db import transaction
from infra.email import InboundEmail, InboundEmailRouter

#
# Routes
#
#

router = InboundEmailRouter()


@router.register_handler(lambda: settings.research_email_from)
async def handle_research_email(email: InboundEmail) -> None:
    logger.info(f"Received research email from {email.sender}: {email.subject}. Headers: {email.message_headers}")
    sender_address = EmailAddress.parse_safe(email.sender)
    if not sender_address:
        return

    user = (
        await User.filter(User.filters.by_any_email([sender_address.email])).prefetch_related("organization").first()
    )
    if not user:
        return

    body = _build_research_body(email.subject, email.stripped_text or email.body_plain)
    if not body:
        logger.warning(f"Research email from {sender_address.email} had no content")
        return

    message_id = email.message_headers.get("Message-ID")
    replying_to_message_id = email.message_headers.get("In-Reply-To")
    cc_recipients = _extract_cc_recipients(
        email.to + email.cc,
        exclude=[settings.research_email_from, sender_address.email],
    )

    async with transaction() as connection:
        question = await ResearchQuestion.create(
            body=body,
            sources=[ResearchSource.INTERNAL],
            creator_id=user.id,
            in_reply_to_message_id=message_id,
            in_reply_to_subject=email.subject,
            replying_to_message_id=replying_to_message_id,
            cc_recipients=cc_recipients,
            using_db=connection,
        )
        question.creator = user
        await start_research_from_question(question, connection)


def _build_research_body(subject: str | None, body: str | None) -> str:
    subject = subject.strip() if subject else ""
    body = body.strip() if body else ""

    if subject and body:
        return f"{subject}\n\n{body}"
    return subject or body


def _extract_cc_recipients(addresses: list[str], exclude: list[str]) -> list[str]:
    exclude_normalized = {e.lower() for e in exclude}
    recipients = []
    for address in addresses:
        parsed = EmailAddress.parse_safe(address)
        if parsed and parsed.email.lower() not in exclude_normalized:
            recipients.append(parsed.email)
    return recipients
