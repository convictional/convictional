from uuid import uuid4

import pytest

from app.models.accounts import User
from app.models.workspaces.email.thread import EmailMessage, EmailReply
from config.enums import EmailReplyType


@pytest.mark.asyncio
async def test_subject_normalization():
    test_cases = [
        ("Hello World", "Hello World"),
        ("Re: Hello World", "Hello World"),
        ("RE: Hello World", "Hello World"),
        ("Fwd: Hello World", "Hello World"),
        ("Re: Fwd: Hello World", "Hello World"),
        ("", ""),
    ]

    for input_subject, expected in test_cases:
        assert EmailMessage(subject=input_subject).normalized_subject == expected


def test_email_reply_to_field():
    """Test EmailReply.to property handles Reply-To headers correctly."""
    # Create test user
    replier = User(id=uuid4(), email="replier@example.com")

    # Test case 1: Reply to message without Reply-To header
    original_message = EmailMessage(
        sender="sender@example.com",
        to=["recipient1@example.com", "recipient2@example.com"],
        cc=["cc1@example.com"],
        headers_list=[],
    )

    reply = EmailReply(
        in_reply_to=original_message,
        replier=replier,
        reply_type=EmailReplyType.REPLY,
    )

    # Should reply to sender when no Reply-To header
    assert reply.to == ["sender@example.com"]

    # Test case 2: Reply to message with Reply-To header
    original_message_with_reply_to = EmailMessage(
        sender="sender@example.com",
        to=["recipient1@example.com"],
        cc=[],
        headers_list=[{"name": "Reply-To", "value": "replyto@example.com"}],
    )

    reply_with_reply_to = EmailReply(
        in_reply_to=original_message_with_reply_to, replier=replier, reply_type=EmailReplyType.REPLY
    )

    # Should use Reply-To header instead of sender
    assert reply_with_reply_to.to == ["replyto@example.com"]

    # Test case 3: When replying to your own message, reply to original recipients
    self_reply_message = EmailMessage(
        sender="replier@example.com",
        to=["recipient@example.com"],
        cc=[],
        headers_list=[],
    )

    self_reply = EmailReply(in_reply_to=self_reply_message, replier=replier, reply_type=EmailReplyType.REPLY)

    # Should reply to original recipients when replying to your own message
    assert self_reply.to == ["recipient@example.com"]

    # Test case 4: Self-reply with multiple original recipients
    self_reply_multiple = EmailMessage(
        sender="replier@example.com",
        to=["recipient1@example.com", "recipient2@example.com"],
        cc=[],
        headers_list=[],
    )

    self_reply_multi = EmailReply(in_reply_to=self_reply_multiple, replier=replier, reply_type=EmailReplyType.REPLY)

    # Should include all original recipients
    assert self_reply_multi.to == ["recipient1@example.com", "recipient2@example.com"]

    # Test case 5: Reply-All has same To behavior as Reply
    reply_all = EmailReply(in_reply_to=original_message, replier=replier, reply_type=EmailReplyType.REPLY_ALL)

    assert reply_all.to == ["sender@example.com"]


def test_email_reply_cc_field():
    """Test EmailReply.cc property handles reply-all correctly."""
    # Create test user
    replier = User(id=uuid4(), email="replier@example.com")

    # Test case 1: Regular reply should have no CC
    original_message = EmailMessage(
        sender="sender@example.com",
        to=["recipient1@example.com", "recipient2@example.com"],
        cc=["cc1@example.com", "cc2@example.com"],
        headers_list=[],
    )

    reply = EmailReply(in_reply_to=original_message, replier=replier, reply_type=EmailReplyType.REPLY)

    # Regular reply should have empty CC
    assert reply.cc == []

    # Test case 2: Reply-all should include original To + CC recipients
    reply_all = EmailReply(in_reply_to=original_message, replier=replier, reply_type=EmailReplyType.REPLY_ALL)

    # Should include all original To recipients (except sender who goes to To field)
    # and all original CC recipients (formatted as display strings)
    expected_cc = [
        "recipient1 <recipient1@example.com>",
        "recipient2 <recipient2@example.com>",
        "cc1 <cc1@example.com>",
        "cc2 <cc2@example.com>",
    ]
    assert sorted(reply_all.cc) == sorted(expected_cc)

    # Test case 3: Reply-all should exclude replier from CC
    message_with_replier_in_cc = EmailMessage(
        sender="sender@example.com",
        to=["recipient@example.com"],
        cc=["replier@example.com", "other@example.com"],
        headers_list=[],
    )

    reply_all_with_self = EmailReply(
        in_reply_to=message_with_replier_in_cc, replier=replier, reply_type=EmailReplyType.REPLY_ALL
    )

    # Should exclude replier from CC but include others (formatted as display strings)
    assert sorted(reply_all_with_self.cc) == sorted(["recipient <recipient@example.com>", "other <other@example.com>"])

    # Test case 4: Reply-all with Reply-To header should exclude Reply-To from CC
    message_with_reply_to = EmailMessage(
        sender="sender@example.com",
        to=["replyto@example.com", "recipient@example.com"],
        cc=["cc1@example.com"],
        headers_list=[{"name": "Reply-To", "value": "replyto@example.com"}],
    )

    reply_all_with_reply_to = EmailReply(
        in_reply_to=message_with_reply_to, replier=replier, reply_type=EmailReplyType.REPLY_ALL
    )

    # Should exclude Reply-To address from CC (it goes to To field)
    assert sorted(reply_all_with_reply_to.cc) == sorted(["recipient <recipient@example.com>", "cc1 <cc1@example.com>"])

    # Test case 5: Complex scenario with overlapping addresses
    complex_message = EmailMessage(
        sender="sender@example.com",
        to=["replier@example.com", "recipient1@example.com"],  # Replier in To
        cc=["recipient2@example.com", "sender@example.com"],  # Sender in CC
        headers_list=[],
    )

    complex_reply_all = EmailReply(in_reply_to=complex_message, replier=replier, reply_type=EmailReplyType.REPLY_ALL)

    # Should exclude replier and sender (who goes to To field)
    assert sorted(complex_reply_all.cc) == sorted(
        ["recipient1 <recipient1@example.com>", "recipient2 <recipient2@example.com>"]
    )
