from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status

from app.jobs.content import ContentIndexingJob, IndexChatJob
from app.models.collaboration.content import IndexingID, IndexMetadata, LookupSearchMetric, SearchableData
from app.models.collaboration.workspace import Visit
from app.models.commands import QuickLink
from app.models.workspaces.email.thread import EmailThread
from config.enums import ContentCategory, ContentType, Sharing
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_chat,
    create_chat_message,
    create_collaborator,
    create_content,
    create_email_contact,
    create_email_message,
    create_meeting,
    create_user,
)


@pytest.mark.asyncio
async def test_api_commands_lists_system_and_quick_links_sorted(client: AppClient):
    user = await client.get_default_user()

    # Quick links sort alphabetically alongside system commands ("Research", "Create quick link").
    await QuickLink.create(label="Alpha Link", url="https://alpha.example.com", owner_id=user.id)
    await QuickLink.create(label="Zeta Link", url="https://zeta.example.com", owner_id=user.id)

    response = await client.get("/api/commands")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    labels = [c["label"] for c in data["commands"]]
    assert labels == sorted(labels, key=str.lower)
    assert "Research" in labels
    assert "Create quick link" in labels
    assert "Alpha Link" in labels
    assert "Zeta Link" in labels

    research = next(c for c in data["commands"] if c["label"] == "Research")
    assert research["type"] == "research"
    assert research["quick_link_id"] is None

    alpha = next(c for c in data["commands"] if c["label"] == "Alpha Link")
    assert alpha["type"] == "quick_link"
    assert alpha["url"] == "https://alpha.example.com"
    assert alpha["quick_link_id"] is not None
    assert alpha["options"] == {"open_in_new_tab": False, "editable": True}


@pytest.mark.asyncio
async def test_api_commands_only_returns_callers_quick_links(client: AppClient):
    user = await client.get_default_user()
    other = await create_user(organization_id=user.organization_id)
    await QuickLink.create(label="Mine", url="https://mine.example.com", owner_id=user.id)
    await QuickLink.create(label="Theirs", url="https://theirs.example.com", owner_id=other.id)

    response = await client.get("/api/commands")
    labels = [c["label"] for c in response.json()["commands"]]
    assert "Mine" in labels
    assert "Theirs" not in labels


@pytest.mark.asyncio
async def test_api_commands_recent_returns_visits_with_collaborators(client: AppClient):
    user = await client.get_default_user()
    other = await create_user(name="Other Person", organization_id=user.organization_id)

    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id, title="Quarterly Sync")
    await client.post(f"/api/workspaces/{meeting.workspace_id}/collaborators", json={"user_id": str(other.id)})
    await Visit.record(user.id, meeting.workspace_id)

    response = await client.get("/api/commands/recent")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert len(data["recent_items"]) == 1
    item = data["recent_items"][0]
    assert item["title"] == "Quarterly Sync"
    assert item["resource_type"] == "Meeting"
    assert item["url"].startswith("http")
    collaborator_names = {c["display_name"] for c in item["collaborators"]}
    assert "Other Person" in collaborator_names


@pytest.mark.asyncio
async def test_api_commands_recent_filters_deleted_resources(client: AppClient):
    user = await client.get_default_user()

    active = await create_meeting(creator_id=user.id, organization_id=user.organization_id, title="Active")
    deleted = await create_meeting(creator_id=user.id, organization_id=user.organization_id, title="Deleted")
    await Visit.record(user.id, active.workspace_id)
    await Visit.record(user.id, deleted.workspace_id)
    await deleted.delete()

    response = await client.get("/api/commands/recent")
    titles = [i["title"] for i in response.json()["recent_items"]]
    assert "Active" in titles
    assert "Deleted" not in titles


@pytest.mark.asyncio
async def test_api_commands_recent_renders_chat(client: AppClient):
    alice = await create_user(name="Alice")
    bob = await create_user(name="Bob", organization_id=alice.organization_id)

    chat = await create_chat(organization_id=alice.organization_id, title=None)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    await create_chat_message(chat_id=chat.id, user_id=bob.id, content="<p>Hey there</p>")
    await Visit.record(alice.id, chat.workspace_id)

    with client.current_user_as(alice):
        response = await client.get("/api/commands/recent")

    assert response.status_code == status.HTTP_200_OK
    item = response.json()["recent_items"][0]
    assert item["title"] == "Alice and Bob"
    assert item["preview"] == "Bob: Hey there"


@pytest.mark.asyncio
async def test_api_commands_lookup_short_query_returns_empty(client: AppClient):
    await client.get_default_user()

    response = await client.get("/api/commands/lookup?query=")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["query"] == ""
    assert data["results"]["user_results"] == []
    assert data["results"]["other_results"] == []

    response = await client.get("/api/commands/lookup?query=a")
    short_results = response.json()["results"]
    assert short_results["user_results"] == []
    assert short_results["other_results"] == []


@pytest.mark.real_embeddings
@pytest.mark.asyncio
async def test_api_commands_lookup_returns_split_results(client: AppClient):
    user = await client.get_default_user()

    # People (users and external contacts) belong in user_results; content belongs in other_results.
    other_user = await create_user(organization_id=user.organization_id, name="Findable User")
    await ContentIndexingJob.from_model(user.organization_id, other_user).perform()

    contact = await create_email_contact(
        organization_id=user.organization_id,
        user_id=user.id,
        email="findable-contact@example.com",
        name="Findable Contact",
    )
    await ContentIndexingJob.from_model(user.organization_id, contact).perform()

    content = await create_content(organization_id=user.organization_id)
    await content.fetch_related("organization")
    await content.indexer.index(
        SearchableData("Findable Document", "Body about Findable", "https://example.com/doc", "Findable User"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.DOCUMENT, Sharing.ORGANIZATION),
    )

    response = await client.get("/api/commands/lookup?query=Findable")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    user_titles = [r["title"] for r in data["results"]["user_results"]]
    other_titles = [r["title"] for r in data["results"]["other_results"]]
    assert "Findable User" in user_titles
    assert "Findable Contact" in user_titles
    assert "Findable Contact" not in other_titles
    assert "Findable Document" in other_titles

    user_result = next(r for r in data["results"]["user_results"] if r["title"] == "Findable User")
    assert user_result["email"] == other_user.email
    assert user_result["global_id"] == str(other_user.global_id)
    assert user_result["content_type"] == "user"

    contact_result = next(r for r in data["results"]["user_results"] if r["title"] == "Findable Contact")
    assert contact_result["content_type"] == "email_contact"
    assert contact_result["email"] == contact.email
    assert contact_result["global_id"] == str(contact.global_id)

    doc_result = next(r for r in data["results"]["other_results"] if r["title"] == "Findable Document")
    assert doc_result["authors"] == ["Findable User"]
    assert doc_result["content_type"] == "document"


@pytest.mark.real_embeddings
@pytest.mark.asyncio
async def test_api_commands_lookup_marks_shared_email_thread(client: AppClient):
    owner = await client.get_default_user()
    collaborator = await create_user(organization_id=owner.organization_id)

    email_message = await create_email_message(
        user_id=owner.id,
        organization_id=owner.organization_id,
        subject="Shared Thread Sample",
        external_thread_id="shared_api_test",
    )
    email_thread = await EmailThread.get(id=email_message.thread_id)
    await email_thread.fetch_related("workspace__collaborators__user", "creator")

    await client.post(
        f"/api/workspaces/{email_thread.workspace_id}/collaborators", json={"user_id": str(collaborator.id)}
    )
    await ContentIndexingJob.from_model(owner.organization_id, email_thread).perform()

    with client.current_user_as(collaborator):
        response = await client.get("/api/commands/lookup?query=Shared Thread Sample")
        thread_result = next(
            r for r in response.json()["results"]["other_results"] if r["title"] == "Shared Thread Sample"
        )
        assert thread_result["shared_with_me"] is True

    with client.current_user_as(owner):
        response = await client.get("/api/commands/lookup?query=Shared Thread Sample")
        thread_result = next(
            r for r in response.json()["results"]["other_results"] if r["title"] == "Shared Thread Sample"
        )
        assert thread_result["shared_with_me"] is False


@pytest.mark.real_embeddings
@pytest.mark.asyncio
async def test_api_commands_lookup_pins_chat_first(client: AppClient):
    user = await client.get_default_user()

    post = await create_content(organization_id=user.organization_id)
    await post.fetch_related("organization")
    await post.indexer.index(
        SearchableData("Widget Plan Post", "Widget rollout plan", "https://example.com/post", "Jane"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST, Sharing.ORGANIZATION),
    )

    chat = await create_chat(organization_id=user.organization_id, title="Widget Plan Chat")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_chat_message(chat_id=chat.id, user_id=user.id, content="Progress update")
    await IndexChatJob(
        indexing_id=IndexingID(organization_id=user.organization_id, source_id=str(chat.global_id))
    ).perform()

    response = await client.get("/api/commands/lookup?query=Widget")
    other_results = response.json()["results"]["other_results"]
    assert other_results[0]["title"] == "Widget Plan Chat"
    assert other_results[0]["content_type"] == "chat"


@pytest.mark.asyncio
async def test_api_commands_people_filters_by_user(client: AppClient):
    user = await client.get_default_user()
    second_user = await create_user(organization_id=user.organization_id, name="Second")

    shared = await create_content(organization_id=user.organization_id)
    await shared.fetch_related("organization")
    await shared.indexer.index(
        SearchableData("Shared Report Doc", "details", "https://example.com/shared", second_user.email),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.FILE,
            force_sharing=Sharing.PRIVATE,
            allowed_user_ids=[user.id, second_user.id],
        ),
    )
    unrelated = await create_content(organization_id=user.organization_id)
    await unrelated.fetch_related("organization")
    await unrelated.indexer.index(
        SearchableData("Other Report Doc", "details", "https://example.com/other", "Someone Else"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.FILE,
            force_sharing=Sharing.PRIVATE,
            allowed_user_ids=[user.id],
        ),
    )

    response = await client.get(f"/api/commands/people?author_gid={second_user.global_id}&query=Report")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    titles = [r["title"] for r in data["results"]["other_results"]]
    assert "Shared Report Doc" in titles
    assert "Other Report Doc" not in titles

    assert data["filter"]["kind"] == "user"
    assert data["filter"]["id"] == str(second_user.id)
    assert data["filter"]["name"] == second_user.display_name
    assert data["filter"]["email"] == second_user.email


@pytest.mark.asyncio
async def test_api_commands_people_cross_org_returns_empty_filter(client: AppClient):
    await client.get_default_user()
    foreign = await create_user()  # different organization

    response = await client.get(f"/api/commands/people?author_gid={foreign.global_id}&query=anything")
    data = response.json()
    assert data["results"]["user_results"] == []
    assert data["results"]["other_results"] == []
    assert data["filter"] is None


@pytest.mark.asyncio
async def test_api_commands_people_with_email_contact_filter(client: AppClient):
    user = await client.get_default_user()

    contact = await create_email_contact(
        organization_id=user.organization_id, user_id=user.id, email="contact@example.com", name="Some Contact"
    )

    email_message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="contact_api_test",
        subject="Hello Contact",
        sender="user@example.com",
        to=["contact@example.com"],
    )
    email_thread = await EmailThread.get(id=email_message.thread_id)
    await ContentIndexingJob.from_model(user.organization_id, email_thread).perform()

    response = await client.get(f"/api/commands/people?author_gid={contact.global_id}&query=Hello")
    data = response.json()
    assert data["filter"]["kind"] == "contact"
    assert data["filter"]["name"] == "Some Contact"
    titles = [r["title"] for r in data["results"]["other_results"]]
    assert "Hello Contact" in titles


@pytest.mark.asyncio
async def test_api_commands_lookup_track_creates_metric(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)

    content1 = await create_content(organization_id=user.organization_id)
    content2 = await create_content(organization_id=user.organization_id)

    response = await client.post(
        "/api/commands/lookup/track",
        json={
            "query": "api query",
            "result_count": 2,
            "result_ids": [str(content1.id), str(content2.id)],
            "clicked_content_id": str(content1.id),
            "clicked_position": 0,
            "filter_author_gid": str(other_user.global_id),
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    metric = await LookupSearchMetric.filter(query="api query").first()
    assert metric is not None
    assert metric.user_id == user.id
    assert metric.organization_id == user.organization_id
    assert metric.result_count == 2
    assert metric.clicked_content_id == content1.id
    assert metric.clicked_position == 0
    assert metric.filter_author_gid == str(other_user.global_id)


@pytest.mark.asyncio
async def test_api_commands_lookup_track_rejects_invalid_input(client: AppClient):
    await client.get_default_user()

    # Bad UUID in clicked_content_id is rejected by Pydantic, not silently swallowed by the DB layer.
    response = await client.post(
        "/api/commands/lookup/track",
        json={
            "query": "garbage",
            "result_count": 0,
            "result_ids": [],
            "clicked_content_id": "not-a-uuid",
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Oversized query is rejected.
    response = await client.post(
        "/api/commands/lookup/track",
        json={"query": "x" * 5000, "result_count": 0, "result_ids": []},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.real_embeddings
@pytest.mark.asyncio
async def test_api_commands_lookup_meeting_display_at_uses_scheduled_at(client: AppClient):
    user = await client.get_default_user()

    scheduled_at = datetime.now(UTC) + timedelta(days=3)
    meeting = await create_meeting(
        creator_id=user.id,
        organization_id=user.organization_id,
        title="Scheduled Sync Sample",
        scheduled_at=scheduled_at,
    )
    await ContentIndexingJob.from_model(user.organization_id, meeting).perform()

    response = await client.get("/api/commands/lookup?query=Scheduled Sync Sample")
    result = next(r for r in response.json()["results"]["other_results"] if r["title"] == "Scheduled Sync Sample")

    assert result["content_type"] == "meeting"
    assert datetime.fromisoformat(result["display_at"]) == scheduled_at
    assert result["display_at"] != result["updated_at"]


@pytest.mark.asyncio
async def test_api_commands_people_rejects_other_users_contact(client: AppClient):
    user = await client.get_default_user()
    other = await create_user(organization_id=user.organization_id)

    # Contact owned by another user in the same org — must not resolve into a filter.
    foreign_contact = await create_email_contact(
        organization_id=user.organization_id,
        user_id=other.id,
        email="not-yours@example.com",
        name="Not Yours",
    )

    response = await client.get(f"/api/commands/people?author_gid={foreign_contact.global_id}&query=anything")
    data = response.json()
    assert data["results"]["user_results"] == []
    assert data["results"]["other_results"] == []
    assert data["filter"] is None
