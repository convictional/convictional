import types

from app.models.collaboration.mailbox import MailboxEntry
from app.models.workspaces.email.address import EmailAddress
from app.presenters.mailbox_entries import MailboxEntryPresenter


class _TestPresenter(MailboxEntryPresenter):
    @property
    def email_thread(self):
        return self.resource


def _presenter_with_senders(sender_strings: list[str], current_user_email: str | None = None):
    """Build a presenter with a fake email thread resource providing sender data."""
    addresses: list[EmailAddress] = [a for s in sender_strings if (a := EmailAddress.parse_safe(s)) is not None]

    unique: dict[str, EmailAddress] = {}
    for a in addresses:
        if a.display_name not in unique:
            unique[a.display_name] = a

    thread = types.SimpleNamespace(
        sender_addresses_chronological=addresses,
        sender_addresses_unique=list(unique.values()),
    )

    mailbox_entry = MailboxEntry()
    presenter = _TestPresenter.create(mailbox_entry, current_user_email=current_user_email)
    presenter.resource = thread
    return presenter


def test_most_recent_sender_single_sender():
    presenter = _presenter_with_senders(["Alice Smith <alice@example.com>"])
    assert presenter.original_sender.email == "alice@example.com"
    assert presenter.most_recent_sender is None
    assert presenter.count_senders == 1


def test_most_recent_sender_two_senders():
    presenter = _presenter_with_senders(["Alice Smith <alice@example.com>", "Bob Johnson <bob@example.com>"])
    assert presenter.original_sender.email == "alice@example.com"
    assert presenter.most_recent_sender.email == "bob@example.com"
    assert presenter.count_senders == 2


def test_most_recent_sender_three_senders():
    presenter = _presenter_with_senders(
        [
            "Alice Smith <alice@example.com>",
            "Bob Johnson <bob@example.com>",
            "Charlie Brown <charlie@example.com>",
        ]
    )
    assert presenter.original_sender.email == "alice@example.com"
    assert presenter.most_recent_sender.email == "charlie@example.com"
    assert presenter.count_senders == 3
    assert presenter.additional_sender_count == 1


def test_most_recent_sender_skips_current_user():
    presenter = _presenter_with_senders(
        [
            "Alice Smith <alice@example.com>",
            "Bob Johnson <bob@example.com>",
            "Owner <owner@example.com>",
        ],
        current_user_email="owner@example.com",
    )
    assert presenter.original_sender.email == "alice@example.com"
    assert presenter.most_recent_sender.email == "bob@example.com"


def test_most_recent_sender_skips_multiple_current_user_messages():
    presenter = _presenter_with_senders(
        [
            "Alice Smith <alice@example.com>",
            "Bob Johnson <bob@example.com>",
            "Owner <owner@example.com>",
            "Owner <owner@example.com>",
        ],
        current_user_email="owner@example.com",
    )
    assert presenter.most_recent_sender.email == "bob@example.com"


def test_most_recent_sender_same_as_original_with_others():
    presenter = _presenter_with_senders(
        [
            "Alice Smith <alice@example.com>",
            "Bob Johnson <bob@example.com>",
            "Alice Smith <alice@example.com>",
        ]
    )
    assert presenter.original_sender.email == "alice@example.com"
    assert presenter.most_recent_sender.email == "alice@example.com"
    assert presenter.count_senders == 2
    assert presenter.additional_sender_count == 1


def test_most_recent_sender_none_when_only_sender_repeats():
    presenter = _presenter_with_senders(
        [
            "Alice Smith <alice@example.com>",
            "Alice Smith <alice@example.com>",
        ]
    )
    assert presenter.original_sender.email == "alice@example.com"
    assert presenter.most_recent_sender is None
    assert presenter.count_senders == 1


def test_most_recent_sender_empty_senders():
    presenter = _presenter_with_senders([])
    assert presenter.original_sender is None
    assert presenter.most_recent_sender is None
    assert presenter.count_senders == 0
