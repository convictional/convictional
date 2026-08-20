import pytest

from app.models.collaboration.mailbox import MailboxEntry
from app.models.workspaces.email.client import FakeEmailClient, local_user_for_address
from app.models.workspaces.email.thread import EmailThread
from config.enums import EmailMessageType
from tests.helpers.factories import create_email_alias, create_email_draft, create_user


async def _send_via_fake_client(sender, addresses: list[str]) -> None:
    draft = await create_email_draft(
        organization_id=sender.organization_id,
        user_id=sender.id,
        subject="Hi there",
        to=addresses,
        body_plain="hello body",
    )
    draft.message.message_type = EmailMessageType.SENDING
    await draft.message.save()
    thread = await EmailThread.get(id=draft.thread_id)
    await FakeEmailClient().send_message(email_thread_id=thread.id, user_id=sender.id)


@pytest.mark.asyncio
async def test_local_user_for_address_resolves_formats_and_aliases():
    user = await create_user()
    await create_email_alias(user_id=user.id, address="alias@example.com")

    # Bare primary, display-name primary, angle-bracket primary, and alias all resolve.
    resolves_to_user = [
        user.email,
        f"Some Name <{user.email}>",
        f"<{user.email}>",
        "alias@example.com",
        '"Quoted Name" <alias@example.com>',
    ]
    for address in resolves_to_user:
        resolved = await local_user_for_address(address)
        assert resolved is not None and resolved.id == user.id, f"{address!r} did not resolve to the user"

    # Unknown address and unparseable garbage resolve to nobody, without raising.
    assert await local_user_for_address("nobody@example.com") is None
    assert await local_user_for_address("not-an-email") is None


@pytest.mark.asyncio
async def test_fake_client_delivers_once_when_primary_and_alias_both_addressed():
    sender = await create_user()
    recipient = await create_user(organization_id=sender.organization_id)
    await create_email_alias(user_id=recipient.id, address="dup-alias@example.com")

    # Both the primary address and an alias for the same user are addressed.
    await _send_via_fake_client(sender, [recipient.email, "dup-alias@example.com"])

    entries = await MailboxEntry.filter(owner_id=recipient.id).all()
    assert len(entries) == 1
