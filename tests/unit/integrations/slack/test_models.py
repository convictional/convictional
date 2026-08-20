from integrations.slack.models import ExpandedMessageContext, SlackMessage


def create_slack_message(
    text: str,
    username: str = "user",
    timestamp: str = "1234567890.000000",
    channel_name: str = "general",
    permalink: str = "https://slack.com/archives/C123/p1234567890000000",
) -> SlackMessage:
    return SlackMessage(
        message_id=f"msg_{timestamp}",
        channel_id="C123",
        channel_name=channel_name,
        text=text,
        timestamp=timestamp,
        username=username,
        permalink=permalink,
        team_id="T123",
    )


#
# Test ExpandedMessageContext
#
#


def test_thread_reply_shows_full_thread_with_matched_marker():
    matched = create_slack_message("This is a reply", username="replier", timestamp="1234567892.000000")
    parent = create_slack_message("Parent message", username="parent_user", timestamp="1234567890.000000")
    other_reply = create_slack_message("Another reply", username="other", timestamp="1234567891.000000")

    context = ExpandedMessageContext(
        matched_message=matched,
        is_thread_reply=True,
        full_thread=[parent, other_reply, matched],
    )

    result = context.to_text()

    assert "Channel: #general" in result
    assert "search matched a reply within this thread" in result
    assert "parent_user: Parent message" in result
    assert "other: Another reply" in result
    assert "[MATCHED] replier: This is a reply" in result


def test_top_level_message_with_surrounding_context():
    prior = create_slack_message("Before message", username="alice", timestamp="1234567889.000000")
    matched = create_slack_message("Matched message", username="bob", timestamp="1234567890.000000")
    subsequent = create_slack_message("After message", username="charlie", timestamp="1234567891.000000")

    context = ExpandedMessageContext(
        matched_message=matched,
        prior_messages=[prior],
        subsequent_messages=[subsequent],
    )

    result = context.to_text()

    assert "Channel: #general" in result
    assert "Messages in channel around the matched message" in result
    assert "alice: Before message" in result
    assert "[MATCHED] bob: Matched message" in result
    assert "charlie: After message" in result


def test_top_level_message_with_thread_replies():
    matched = create_slack_message("Parent message", username="bob", timestamp="1234567890.000000")
    reply1 = create_slack_message("First reply", username="alice", timestamp="1234567891.000000")
    reply2 = create_slack_message("Second reply", username="charlie", timestamp="1234567892.000000")

    context = ExpandedMessageContext(
        matched_message=matched,
        thread_replies=[reply1, reply2],
    )

    result = context.to_text()

    assert "Channel: #general" in result
    assert "[MATCHED] bob: Parent message" in result
    assert "Thread replies to the matched message" in result
    assert "  alice: First reply" in result
    assert "  charlie: Second reply" in result


def test_standalone_message_without_context():
    matched = create_slack_message("Solo message", username="bob")

    context = ExpandedMessageContext(matched_message=matched)

    result = context.to_text()

    assert "Channel: #general" in result
    assert "[MATCHED] bob: Solo message" in result
    assert "Thread replies" not in result
    assert "Messages in channel" not in result


def test_surrounding_context_with_thread_replies():
    prior = create_slack_message("Before", username="alice", timestamp="1234567889.000000")
    matched = create_slack_message("Main message", username="bob", timestamp="1234567890.000000")
    reply = create_slack_message("Reply to main", username="charlie", timestamp="1234567891.000000")

    context = ExpandedMessageContext(
        matched_message=matched,
        prior_messages=[prior],
        thread_replies=[reply],
    )

    result = context.to_text()

    assert "alice: Before" in result
    assert "[MATCHED] bob: Main message" in result
    assert "Thread replies to the matched message" in result
    assert "  charlie: Reply to main" in result
