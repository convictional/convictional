import pytest
from freezegun import freeze_time

from app.jobs.research import ResearchJob
from app.models.accounts import OAuthToken
from app.models.collaboration.content import IndexMetadata, Research, ResearchIteration, SearchableData
from config.enums import AuthenticationProvider, ContentCategory, ContentType, Integration, ResearchSource, Sharing
from infra.jobs import JobsOutbox
from integrations.slack.models import SlackContent
from tests.helpers.factories import create_content, create_user

# To re-record new VCR cassettes, replace with a valid Slack OAuth token with appropriate scopes
# The easiest way to get a token is to authenticate via the Slack OAuth flow in the application
# and then retrieve it from the OAuthToken model in the database.
SLACK_TEST_TOKEN = "xoxp-TEST-TOKEN-FOR-RE-RECORDING-REPLACE-WITH-VALID-TOKEN"


@pytest.mark.real_embeddings
@pytest.mark.asyncio
@pytest.mark.requires_config
@freeze_time("2025-12-09 20:32:43", tz_offset=0)
async def test_research_job_with_slack_source():
    user = await create_user()
    await user.fetch_related("organization")
    await user.add_integration(Integration.SLACK)
    await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.SLACK,
        access_token=SLACK_TEST_TOKEN,
        scope="channels:read,users:read,search:read",
    )

    # Content IDs are hardcoded to ensure the same content is used in the cassette request bodies
    first = await create_content(id="a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d", organization=user.organization)
    await first.indexer.index(
        SearchableData("Project update", "Team discussed project timeline", "https://example.com/update", "Alice"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    research = await Research.create(
        topic="What has the team discussed in Slack about project updates?",
        sources=[ResearchSource.INTERNAL, ResearchSource.SLACK],
        max_depth=1,
        max_breadth=3,
        creator_id=user.id,
        organization_id=user.organization_id,
    )

    async with JobsOutbox():
        await ResearchJob(research_id=research.id).perform()

    iterations = await ResearchIteration.all().prefetch_related("queries")
    assert len(iterations) > 0

    all_queries = [query for iteration in iterations for query in iteration.queries]
    slack_queries = [q for q in all_queries if q.source == ResearchSource.SLACK]

    assert len(slack_queries) > 0, "Expected at least one Slack query"
    assert all(q.source in (ResearchSource.INTERNAL, ResearchSource.SLACK) for q in all_queries)

    all_slack_content = await SlackContent.all()
    assert len(all_slack_content) > 0, "Expected SlackContent to be persisted in the database"

    # Slack content includes thread replies and surrounding messages
    slack_content = all_slack_content[0]
    assert "Thread replies to the matched message" in slack_content.index_content

    slack_queries_with_results = [q for q in slack_queries if len(q.content_result_ids) > 0]
    assert len(slack_queries_with_results) > 0, "Expected at least one Slack query to have content results"
    for query in slack_queries_with_results:
        assert all(id is not None for id in query.content_result_ids), "content_result_ids should not contain None"

    await research.refresh_from_db()
    await research.fetch_related("iterations__queries")
    assert research.is_completed


@pytest.mark.real_embeddings
@pytest.mark.asyncio
@pytest.mark.requires_config
@freeze_time("2025-12-09 20:32:25", tz_offset=0)
async def test_research_job_with_nested_slack_comment():
    user = await create_user()
    await user.fetch_related("organization")
    await user.add_integration(Integration.SLACK)
    await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.SLACK,
        access_token=SLACK_TEST_TOKEN,
        scope="channels:read,users:read,search:read",
    )

    # Content IDs are hardcoded to ensure the same content is used in the cassette request bodies
    first = await create_content(id="a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d", organization=user.organization)
    await first.indexer.index(
        SearchableData("Project update", "Team discussed project timeline", "https://example.com/update", "Alice"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    # Query designed to return a message that is a reply in a thread
    research = await Research.create(
        topic="Search slack for 'resolving users, and expanding context'",
        sources=[ResearchSource.INTERNAL, ResearchSource.SLACK],
        max_depth=1,
        max_breadth=3,
        creator_id=user.id,
        organization_id=user.organization_id,
    )

    async with JobsOutbox():
        await ResearchJob(research_id=research.id).perform()

    all_slack_content = await SlackContent.all()
    assert len(all_slack_content) > 0, "Expected SlackContent to be persisted in the database"

    # Slack content includes thread replies and surrounding messages
    slack_content = all_slack_content[0]
    assert "search matched a reply within this thread" in slack_content.index_content
    assert "[MATCHED]" in slack_content.index_content
