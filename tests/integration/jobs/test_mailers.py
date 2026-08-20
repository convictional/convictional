import pytest

from app.jobs.mailers import SendNewUserEmailJob, SendResearchQuestionEmailJob, UserInvitedEmailJob
from app.models.collaboration.content import Research
from app.models.workspaces.email.address import EmailAddress
from config import settings
from config.enums import ResearchSource
from infra.email import FakeDelivery
from tests.helpers.factories import create_organization, create_research_question, create_user


@pytest.fixture(autouse=True)
def new_user_notification_emails():
    # The addresses notified of a signup are an operator's to choose, so the setting has no
    # default and the job sends nowhere until one is configured. The autouse
    # `custom_settings` fixture restores it after the test.
    settings.new_user_notification_emails = "signups@example.com"


def new_user_notification_recipient() -> str:
    return ", ".join(EmailAddress.parse_list_addresses(settings.new_user_notification_emails))


@pytest.mark.asyncio
async def test_send_new_user_email_job_sends_signup_notification(email_delivery: FakeDelivery):
    user = await create_user(email="newbie@example.com", bio="hello world")

    await SendNewUserEmailJob(user_id=user.id).perform()

    messages = email_delivery.by_recipient(new_user_notification_recipient())
    assert len(messages) == 1

    message = messages[0]
    assert message.subject == f"[Convictional] New user — {user.display_name} <newbie@example.com>"

    body = message.text or ""
    assert "action:          user.created" in body
    assert f"user_id:         {user.id}" in body
    assert "email:           newbie@example.com" in body
    assert "hello world" in body
    assert f"organization_id: {user.organization_id}" in body


@pytest.mark.asyncio
async def test_send_new_user_email_sends_to_all_configured_recipients(email_delivery: FakeDelivery):
    user = await create_user(email="newbie@example.com")

    with settings.override():
        settings.new_user_notification_emails = "signups@example.com,team@example.com"
        await SendNewUserEmailJob(user_id=user.id).perform()

    assert len(email_delivery.messages) == 1
    assert email_delivery.messages[0].to == "signups@example.com, team@example.com"


@pytest.mark.asyncio
async def test_send_new_user_email_renders_multiline_bio_outside_code_block(email_delivery: FakeDelivery):
    bio = "First paragraph of bio.\n\nSecond paragraph with more detail."
    user = await create_user(email="poet@example.com", bio=bio)

    await SendNewUserEmailJob(user_id=user.id).perform()

    body = email_delivery.by_recipient(new_user_notification_recipient())[0].text or ""
    assert "First paragraph of bio." in body
    assert "Second paragraph with more detail." in body
    # The bio rendering must not break the metadata code block above it
    assert "action:          user.created" in body


@pytest.mark.asyncio
async def test_send_new_user_email_handles_empty_bio(email_delivery: FakeDelivery):
    user = await create_user(email="quiet@example.com", bio="")

    await SendNewUserEmailJob(user_id=user.id).perform()

    body = email_delivery.by_recipient(new_user_notification_recipient())[0].text or ""
    assert "_(none)_" in body or "(none)" in body


HTML_INJECTION_PAYLOADS = [
    "<script>alert('xss')</script>",
    '<img src=x onerror="alert(1)">',
]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", HTML_INJECTION_PAYLOADS)
async def test_user_invited_email_strips_html_from_inviter_org_and_note(email_delivery: FakeDelivery, payload: str):
    organization = await create_organization(name=f"Acme {payload}")
    inviter = await create_user(organization_id=organization.id, name=f"Mallory {payload}")
    invitee = await create_user(organization_id=organization.id, email="newbie@example.com", invited_by_id=inviter.id)

    await UserInvitedEmailJob(user_id=invitee.id, note=f"Hi there {payload}").perform()

    messages = email_delivery.by_recipient("newbie@example.com")
    assert len(messages) == 1
    message = messages[0]

    # No live HTML/event handlers should survive into the rendered HTML body.
    assert "<script" not in message.html
    assert "onerror=" not in message.html
    assert "<img" not in message.html

    # Visible text outside the payload should still render so we know we stripped, not blanked.
    assert "Acme" in message.html
    assert "Mallory" in message.html
    assert "Hi there" in message.html


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", HTML_INJECTION_PAYLOADS)
async def test_send_research_question_email_strips_html_from_body_and_title(
    email_delivery: FakeDelivery, payload: str
):
    user = await create_user(email="researcher@example.com")
    research = await Research.create(
        topic="Test topic",
        sources=[ResearchSource.INTERNAL],
        creator_id=user.id,
        organization_id=user.organization_id,
    )
    question = await create_research_question(
        creator_id=user.id,
        body=f"Tell me about widgets {payload}",
        title=f"Widgets {payload}",
        research_id=research.id,
    )
    await question.mark_completed(response="Some research findings.")

    await SendResearchQuestionEmailJob(research_question_id=question.id).perform()

    messages = email_delivery.by_recipient("researcher@example.com")
    assert len(messages) == 1
    message = messages[0]

    assert "<script" not in message.html
    assert "onerror=" not in message.html
    assert "<img" not in message.html
    assert "<script" not in message.subject
    assert "onerror=" not in message.subject

    assert "widgets" in message.html.lower()
    assert "widgets" in message.subject.lower()


@pytest.mark.asyncio
async def test_send_research_question_email_strips_html_from_in_reply_to_subject(email_delivery: FakeDelivery):
    payload = "<script>alert('reply')</script>"
    user = await create_user(email="researcher@example.com")
    research = await Research.create(
        topic="Test topic",
        sources=[ResearchSource.INTERNAL],
        creator_id=user.id,
        organization_id=user.organization_id,
    )
    question = await create_research_question(
        creator_id=user.id,
        body="Follow-up question",
        research_id=research.id,
        in_reply_to_message_id="<prior@example.com>",
        in_reply_to_subject=f"Earlier thread {payload}",
    )
    await question.mark_completed(response="More findings.")

    await SendResearchQuestionEmailJob(research_question_id=question.id).perform()

    message = email_delivery.by_recipient("researcher@example.com")[0]
    assert "<script" not in message.subject
    assert "Earlier thread" in message.subject


@pytest.mark.asyncio
async def test_send_research_question_email_does_not_resend_when_already_sent(email_delivery: FakeDelivery):
    # A duplicate enqueue or retry must not re-send; response_message_id marks an already-sent answer.
    user = await create_user(email="researcher@example.com")
    research = await Research.create(
        topic="Test topic",
        sources=[ResearchSource.INTERNAL],
        creator_id=user.id,
        organization_id=user.organization_id,
    )
    question = await create_research_question(creator_id=user.id, research_id=research.id)
    await question.mark_completed(response="Some research findings.")
    question.response_message_id = "<already-sent@example.com>"
    await question.save(update_fields=["response_message_id"])

    await SendResearchQuestionEmailJob(research_question_id=question.id).perform()

    assert email_delivery.by_recipient("researcher@example.com") == []
