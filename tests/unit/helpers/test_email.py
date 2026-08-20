from app.helpers.email import format_sender_display
from tests.unit.presenters.test_mailbox_entries import _presenter_with_senders


def test_format_sender_display_two_senders_no_additional():
    presenter = _presenter_with_senders(["Alice Smith <alice@example.com>", "Bob Johnson <bob@example.com>"])
    result = format_sender_display(presenter)
    assert result == "Alice, Bob"


def test_format_sender_display_two_senders_with_additional():
    presenter = _presenter_with_senders(
        [
            "Alice Smith <alice@example.com>",
            "Charlie Brown <charlie@example.com>",
            "Bob Johnson <bob@example.com>",
        ]
    )
    result = format_sender_display(presenter)
    assert result == "Alice..Bob"


def test_format_sender_display_single_sender():
    presenter = _presenter_with_senders(["Alice Smith <alice@example.com>"])
    result = format_sender_display(presenter)
    assert result == "Alice"


def test_format_sender_display_empty_mailbox_entry_presenter():
    presenter = _presenter_with_senders([])
    result = format_sender_display(presenter)
    assert result == "Unknown"


def test_format_sender_display_same_sender_first_and_last_with_others():
    presenter = _presenter_with_senders(
        [
            "Alice Smith <alice@example.com>",
            "Bob Johnson <bob@example.com>",
            "Alice Smith <alice@example.com>",
        ]
    )
    result = format_sender_display(presenter)
    assert result == "Alice..Alice"
