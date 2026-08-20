import pytest

from integrations.slack.client import SlackClient
from integrations.slack.models import SlackMessage

# To re-record new VCR cassettes, replace with a valid Slack OAuth token with appropriate scopes
# The easiest way to get a token is to authenticate via the Slack OAuth flow in the application
# and then retrieve it from the OAuthToken model in the database.
SLACK_TEST_TOKEN = "xoxp-TEST-TOKEN-REPLACE-WITH-VALID-TOKEN"

ALL_DEV_SANDBOX_CHANNEL_ID = "C077BMKNLHF"
TARGET_MESSAGE_TS = 1764860468.176179


@pytest.fixture
def slack_client():
    return SlackClient(access_token=SLACK_TEST_TOKEN)


@pytest.mark.requires_config
@pytest.mark.asyncio
async def test_search_messages(slack_client: SlackClient):
    results = await slack_client.search_messages(query="Project Update", limit=5)

    assert isinstance(results, list)
    assert 0 < len(results) <= 5
    for result in results:
        assert isinstance(result, SlackMessage)
        assert result.message_id
        assert result.channel_id


@pytest.mark.requires_config
@pytest.mark.asyncio
async def test_get_team_info(slack_client: SlackClient):
    response = await slack_client.get_team_info()

    assert isinstance(response, dict)
    assert "team" in response
    assert "id" in response["team"]
    assert "name" in response["team"]


@pytest.mark.requires_config
@pytest.mark.asyncio
async def test_get_conversation_history(slack_client: SlackClient):
    channel_id = ALL_DEV_SANDBOX_CHANNEL_ID

    oldest = TARGET_MESSAGE_TS - 60 * 15
    latest = TARGET_MESSAGE_TS + 60 * 15

    history = await slack_client.get_conversation_history(
        channel_id=channel_id,
        oldest=str(oldest),
        latest=str(latest),
        limit=5,
    )

    assert isinstance(history, list)
    assert 0 < len(history) <= 5
    for message in history:
        assert isinstance(message, SlackMessage)
        assert message.message_id
        assert message.channel_id


@pytest.mark.requires_config
@pytest.mark.asyncio
async def test_get_thread_replies(slack_client: SlackClient):
    channel_id = ALL_DEV_SANDBOX_CHANNEL_ID
    thread_ts = TARGET_MESSAGE_TS

    replies = await slack_client.get_thread_replies(
        channel_id=channel_id,
        thread_ts=str(thread_ts),
        limit=5,
    )

    assert isinstance(replies, list)
    assert 0 < len(replies) <= 5
    for reply in replies:
        assert isinstance(reply, SlackMessage)
        assert reply.message_id
        assert reply.channel_id
