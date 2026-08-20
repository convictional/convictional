from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status

from app.models.collaboration.mailbox import MailboxView, MailboxViewCache, MailboxViewIdentifier
from app.routers.api.mailbox_views import MAILBOX_VIEW_MAX_ENTRIES
from tests.helpers.app import AppClient
from tests.helpers.factories import create_goal, create_mailbox_entry, create_mailbox_view, create_user


@pytest.mark.asyncio
async def test_index_empty(client: AppClient):
    await client.get_default_user()
    response = await client.get("/api/mailbox_views")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["all_views"] == []
    assert body["active"] is None
    assert body["cached_sections"] is None
    assert body["is_not_found"] is False
    # No active view → no coverage counts to report.
    assert body["eligible_entry_count"] is None
    assert body["considered_entry_count"] is None


@pytest.mark.asyncio
async def test_index_reports_coverage_for_active_view(client: AppClient):
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    for i in range(3):
        await create_mailbox_entry(
            title=f"Conversation {i}",
            owner_id=user.id,
            organization_id=user.organization_id,
            last_comment_author_id=user.id,
        )

    response = await client.get(f"/api/mailbox_views?view_id={view.id}")
    body = response.json()
    # All three inbox entries are eligible and (well under the cap) all considered.
    assert body["eligible_entry_count"] == 3
    assert body["considered_entry_count"] == 3


@pytest.mark.asyncio
async def test_index_coverage_caps_considered_at_max(client: AppClient):
    # When the inbox exceeds the cap, eligible reflects the whole inbox but considered is capped —
    # the condition that surfaces the coverage notice. Patch the count to avoid creating 250+ rows.
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)

    class _FakeInboxQuerySet:
        async def count(self) -> int:
            return MAILBOX_VIEW_MAX_ENTRIES + 50

    with patch("app.routers.api.mailbox_views._ai_inbox_queryset", return_value=_FakeInboxQuerySet()):
        response = await client.get(f"/api/mailbox_views?view_id={view.id}")
    body = response.json()
    assert body["eligible_entry_count"] == MAILBOX_VIEW_MAX_ENTRIES + 50
    assert body["considered_entry_count"] == MAILBOX_VIEW_MAX_ENTRIES


@pytest.mark.asyncio
async def test_index_lists_user_views(client: AppClient):
    user = await client.get_default_user()
    view = await create_mailbox_view(
        user_id=user.id, organization_id=user.organization_id, title="My View", view_request="Show me X"
    )

    response = await client.get("/api/mailbox_views")
    body = response.json()
    assert len(body["all_views"]) == 1
    assert body["all_views"][0]["id"] == str(view.id)
    assert body["all_views"][0]["title"] == "My View"


@pytest.mark.asyncio
async def test_index_with_active_view(client: AppClient):
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)

    response = await client.get(f"/api/mailbox_views?view_id={view.id}")
    body = response.json()
    assert body["active"] is not None
    assert body["active"]["kind"] == "view"
    assert body["active"]["id"] == str(view.id)
    # channel_id is the mailbox_view topic identity the React island subscribes by (unsigned).
    assert body["active"]["channel_id"] == str(view.id)
    assert body["is_not_found"] is False


@pytest.mark.asyncio
async def test_index_active_view_not_found_returns_flag(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    other_view = await create_mailbox_view(user_id=other_user.id, organization_id=user.organization_id)

    response = await client.get(f"/api/mailbox_views?view_id={other_view.id}")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["is_not_found"] is True
    assert body["active"] is None


@pytest.mark.asyncio
async def test_index_with_template(client: AppClient):
    await client.get_default_user()
    response = await client.get("/api/mailbox_views?template=urgent_important")
    body = response.json()
    assert body["active"] is not None
    assert body["active"]["kind"] == "template"
    # `id` and `channel_id` are symmetric across kinds — both carry the same opaque identifier.
    assert body["active"]["id"] == "template:urgent_important"
    assert body["active"]["channel_id"] == "template:urgent_important"
    assert body["active"]["requires_goals"] is False


@pytest.mark.asyncio
async def test_index_by_goal_active_title_is_goal_title(client: AppClient):
    # The header reflects which goal a by_goal sort targets on load, before the client lazy-loads
    # the goals list — so the active view's title carries the goal's title (not the generic "By goal").
    user = await client.get_default_user()
    goal = await create_goal(
        organization_id=user.organization_id,
        owner_id=user.id,
        creator_id=user.id,
        title="Hit $10M ARR",
        description="Q4 revenue target",
    )
    response = await client.get(f"/api/mailbox_views?template=by_goal&goal_id={goal.id}")
    body = response.json()
    assert body["active"] is not None
    assert body["active"]["id"] == f"template:by_goal:{goal.id}"
    assert body["active"]["requires_goals"] is True
    assert body["active"]["title"] == "Hit $10M ARR"


@pytest.mark.asyncio
async def test_index_returns_cached_sections_with_goal(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    goal = await create_goal(
        organization_id=user.organization_id,
        owner_id=user.id,
        creator_id=user.id,
        description="Q4 launch",
    )
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    await MailboxViewCache(view).write(
        [
            {
                "title": "Goal section",
                "description": "Things related to the goal",
                "mailbox_entry_ids": [],
                "goal_id": str(goal.id),
            }
        ]
    )

    response = await client.get(f"/api/mailbox_views?view_id={view.id}")
    body = response.json()
    assert body["cached_sections"] is not None
    assert len(body["cached_sections"]) == 1
    section = body["cached_sections"][0]
    assert section["title"] == "Goal section"
    assert section["goal"]["id"] == str(goal.id)
    assert section["goal"]["description"] == "Q4 launch"


@pytest.mark.asyncio
async def test_index_surfaces_generating_flag_for_partial_cache(client: AppClient, use_postgres_cache):
    # A refresh mid-sort hits a partial cache: the index returns the partial sections AND
    # generating=True so the client renders them but keeps the spinner + subscription. A final
    # (completed) cache reports generating=False so the client treats it as done.
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    sections = [{"title": "", "description": "", "mailbox_entry_ids": []}]

    await MailboxViewCache(view).write(sections, generating=True)
    response = await client.get(f"/api/mailbox_views?view_id={view.id}")
    body = response.json()
    assert body["cached_sections"] is not None
    assert body["generating"] is True

    await MailboxViewCache(view).write(sections)
    response = await client.get(f"/api/mailbox_views?view_id={view.id}")
    body = response.json()
    assert body["cached_sections"] is not None
    assert body["generating"] is False


@pytest.mark.asyncio
async def test_index_drops_foreign_org_goal_from_cached_section(client: AppClient, use_postgres_cache):
    # Cached goal_ids come from LLM output and could reference a foreign-org goal via tampering
    # or prompt injection. Hydration re-queries with organization_id, so a foreign goal resolves
    # to no badge (goal=None) rather than leaking another org's goal into the section.
    user = await client.get_default_user()
    stranger = await create_user()
    foreign_goal = await create_goal(
        organization_id=stranger.organization_id,
        owner_id=stranger.id,
        creator_id=stranger.id,
        description="Other org secret",
    )
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    await MailboxViewCache(view).write(
        [
            {
                "title": "Goal section",
                "description": "Things related to the goal",
                "mailbox_entry_ids": [],
                "goal_id": str(foreign_goal.id),
            }
        ]
    )

    response = await client.get(f"/api/mailbox_views?view_id={view.id}")
    body = response.json()
    assert len(body["cached_sections"]) == 1
    assert body["cached_sections"][0]["goal"] is None


@pytest.mark.asyncio
async def test_index_tolerates_malformed_goal_id_in_cached_section(client: AppClient, use_postgres_cache):
    # A cache written before goal_id was sanitized can hold a mangled UUID (the LLM truncates
    # hand-transcribed ids). It must not reach Goal.filter(id__in=...) — that bind error 500s the
    # whole view and wedges the user. The malformed id is dropped to no badge instead.
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    await MailboxViewCache(view).write(
        [
            {
                "title": "Goal section",
                "description": "Things related to the goal",
                "mailbox_entry_ids": [],
                "goal_id": "f9472e54-1",
            }
        ]
    )

    response = await client.get(f"/api/mailbox_views?view_id={view.id}")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["cached_sections"]) == 1
    assert body["cached_sections"][0]["goal"] is None


@pytest.mark.asyncio
async def test_create_with_explicit_title(client: AppClient):
    user = await client.get_default_user()
    response = await client.post(
        "/api/mailbox_views",
        json={"title": "Important", "view_request": "Show me important emails"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["view"]["title"] == "Important"
    assert body["redirect_to"].startswith("/?mailbox_view_id=")

    view = await MailboxView.first()
    assert view is not None
    assert view.user_id == user.id
    assert view.title == "Important"


@pytest.mark.asyncio
async def test_create_generates_title_when_omitted(client: AppClient):
    await client.get_default_user()
    with patch("infra.llm.LLM.string_completion", new=AsyncMock(return_value='"Auto Title"')):
        response = await client.post(
            "/api/mailbox_views",
            json={"view_request": "Important client emails"},
        )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["view"]["title"] == "Auto Title"


@pytest.mark.asyncio
async def test_create_falls_back_to_view_request_when_llm_fails(client: AppClient):
    await client.get_default_user()
    long_request = "Show me everything that mentions Q4 launch and customer feedback "
    with patch("infra.llm.LLM.string_completion", new=AsyncMock(side_effect=RuntimeError("provider down"))):
        response = await client.post("/api/mailbox_views", json={"view_request": long_request})
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["view"]["title"] == long_request[:80].strip()

    view = await MailboxView.first()
    assert view is not None
    assert view.title == long_request[:80].strip()


@pytest.mark.asyncio
async def test_create_caps_generated_title_length(client: AppClient):
    await client.get_default_user()
    overlong_title = "a" * 500
    with patch("infra.llm.LLM.string_completion", new=AsyncMock(return_value=overlong_title)):
        response = await client.post(
            "/api/mailbox_views",
            json={"view_request": "Anything"},
        )
    assert response.status_code == status.HTTP_201_CREATED
    assert len(response.json()["view"]["title"]) == 120


@pytest.mark.asyncio
async def test_create_preserves_explicit_long_title(client: AppClient):
    # The MAX_TITLE_LENGTH cap is defense-in-depth against LLM output. Explicit
    # user-supplied titles pass through unchanged to match the HTML route.
    await client.get_default_user()
    long_title = "a" * 500
    response = await client.post(
        "/api/mailbox_views",
        json={"title": long_title, "view_request": "Anything"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["view"]["title"] == long_title


@pytest.mark.asyncio
async def test_create_rejects_blank_view_request(client: AppClient):
    await client.get_default_user()
    response = await client.post("/api/mailbox_views", json={"view_request": "   "})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_update_view(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    await MailboxViewCache(view).write([{"title": "Cached", "mailbox_entry_ids": []}])
    assert await MailboxViewCache(view).exists()

    # Updating only the title preserves cache
    response = await client.patch(f"/api/mailbox_views/{view.id}", json={"title": "Renamed"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["view"]["title"] == "Renamed"
    assert await MailboxViewCache(view).exists()

    # Updating view_request clears cache
    response = await client.patch(f"/api/mailbox_views/{view.id}", json={"view_request": "Changed request"})
    assert response.status_code == status.HTTP_200_OK
    await view.refresh_from_db()
    assert view.view_request == "Changed request"
    assert not await MailboxViewCache(view).exists()


@pytest.mark.asyncio
async def test_update_ignores_empty_title(client: AppClient):
    # Matches HTML behavior — an empty/whitespace title is dropped, not persisted.
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id, title="Original")

    response = await client.patch(f"/api/mailbox_views/{view.id}", json={"title": ""})
    assert response.status_code == status.HTTP_200_OK
    await view.refresh_from_db()
    assert view.title == "Original"


@pytest.mark.asyncio
async def test_refresh_clears_cache(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    await MailboxViewCache(view).write([{"title": "Cached", "mailbox_entry_ids": []}])
    assert await MailboxViewCache(view).exists()

    response = await client.post(f"/api/mailbox_views/{view.id}/refresh")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not await MailboxViewCache(view).exists()


@pytest.mark.asyncio
async def test_refresh_clears_template_cache(client: AppClient, use_postgres_cache):
    # Built-in template sorts show the same banner but have no MailboxView row — refresh must clear
    # the per-user template cache keyed by template name (and goal_id for the by_goal sort).
    user = await client.get_default_user()
    goal = await create_goal(user_id=user.id, organization_id=user.organization_id)

    plain = MailboxViewIdentifier.for_template("priority")
    by_goal = MailboxViewIdentifier.for_template("by_goal", goal_id=goal.id)
    assert plain and by_goal
    await plain.write_cache(user.id, [{"title": "Cached", "mailbox_entry_ids": []}])
    await by_goal.write_cache(user.id, [{"title": "Cached", "mailbox_entry_ids": []}])

    plain_resp = await client.post("/api/mailbox_views/template:priority/refresh")
    assert plain_resp.status_code == status.HTTP_204_NO_CONTENT
    assert await plain.read_cache(user.id) is None
    # The goal-targeted cache is keyed separately, so the plain refresh leaves it intact.
    assert await by_goal.read_cache(user.id) is not None

    by_goal_resp = await client.post(f"/api/mailbox_views/template:by_goal:{goal.id}/refresh")
    assert by_goal_resp.status_code == status.HTTP_204_NO_CONTENT
    assert await by_goal.read_cache(user.id) is None


@pytest.mark.asyncio
async def test_refresh_template_via_percent_encoded_path(client: AppClient, use_postgres_cache):
    # The client encodes the identifier, so the colons reach the server as %3A. Pin the round-trip
    # here — the readable test above posts raw colons, which isn't what the browser actually sends.
    user = await client.get_default_user()
    ident = MailboxViewIdentifier.for_template("priority")
    assert ident
    await ident.write_cache(user.id, [{"title": "Cached", "mailbox_entry_ids": []}])

    response = await client.post("/api/mailbox_views/template%3Apriority/refresh")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await ident.read_cache(user.id) is None


@pytest.mark.asyncio
async def test_refresh_unknown_identifier_404(client: AppClient):
    await client.get_default_user()
    response = await client.post("/api/mailbox_views/template:not_a_real_template/refresh")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_view(client: AppClient):
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)

    response = await client.delete(f"/api/mailbox_views/{view.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await MailboxView.all().count() == 0


@pytest.mark.asyncio
async def test_actions_404_for_other_user(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    other_view = await create_mailbox_view(user_id=other_user.id, organization_id=user.organization_id)

    patch_resp = await client.patch(f"/api/mailbox_views/{other_view.id}", json={"title": "x"})
    assert patch_resp.status_code == status.HTTP_404_NOT_FOUND
    refresh_resp = await client.post(f"/api/mailbox_views/{other_view.id}/refresh")
    assert refresh_resp.status_code == status.HTTP_404_NOT_FOUND
    delete_resp = await client.delete(f"/api/mailbox_views/{other_view.id}")
    assert delete_resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_layout_round_trips_and_defaults_grouped(client: AppClient):
    await client.get_default_user()
    # Default is grouped when layout is omitted.
    grouped = await client.post("/api/mailbox_views", json={"title": "Grouped", "view_request": "Show X"})
    assert grouped.json()["view"]["layout"] == "grouped"

    # Ranked round-trips through create and the active-view response.
    ranked = await client.post(
        "/api/mailbox_views", json={"title": "Ranked", "view_request": "Rank X", "layout": "ranked"}
    )
    assert ranked.status_code == status.HTTP_201_CREATED
    assert ranked.json()["view"]["layout"] == "ranked"

    ranked_id = ranked.json()["view"]["id"]
    body = (await client.get(f"/api/mailbox_views?view_id={ranked_id}")).json()
    assert body["active"]["layout"] == "ranked"

    view = await MailboxView.get(id=ranked_id)
    assert view.layout == "ranked"


@pytest.mark.asyncio
async def test_create_rejects_invalid_layout(client: AppClient):
    await client.get_default_user()
    # Enum validation fires at request parsing, so a nonsense layout is 422.
    response = await client.post("/api/mailbox_views", json={"view_request": "anything", "layout": "sideways"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_patch_layout_change_invalidates_cache(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    await MailboxViewCache(view).write([{"title": "Cached", "mailbox_entry_ids": []}])
    assert await MailboxViewCache(view).exists()

    # A layout-only PATCH (view_request unchanged) must still invalidate the cache, since the
    # cached shape (grouped sections vs one ranked list) is no longer valid.
    response = await client.patch(f"/api/mailbox_views/{view.id}", json={"layout": "ranked"})
    assert response.status_code == status.HTTP_200_OK
    await view.refresh_from_db()
    assert view.layout == "ranked"
    assert not await MailboxViewCache(view).exists()


@pytest.mark.asyncio
async def test_all_views_split_by_layout_does_not_starve_sorts(client: AppClient):
    # all_views caps each layout independently, so a user with many grouped views never hides their
    # ranked sorts (the client splits the combined list by layout).
    user = await client.get_default_user()
    for i in range(12):
        await create_mailbox_view(
            user_id=user.id, organization_id=user.organization_id, title=f"View {i}", layout="grouped"
        )
    for i in range(3):
        await create_mailbox_view(
            user_id=user.id, organization_id=user.organization_id, title=f"Sort {i}", layout="ranked"
        )

    body = (await client.get("/api/mailbox_views")).json()
    layouts = [v["layout"] for v in body["all_views"]]
    assert layouts.count("grouped") == 10  # capped per layout
    assert layouts.count("ranked") == 3  # not starved by the grouped overflow


@pytest.mark.asyncio
async def test_by_goal_template_threads_goal_into_channel_and_cache(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    goal = await create_goal(organization_id=user.organization_id, owner_id=user.id, creator_id=user.id)

    body = (await client.get(f"/api/mailbox_views?template=by_goal&goal_id={goal.id}")).json()
    assert body["active"]["kind"] == "template"
    assert body["active"]["layout"] == "ranked"
    assert body["active"]["requires_goals"] is True
    # goal_id rides the opaque wire string so two goals never collide on one channel.
    assert body["active"]["channel_id"] == f"template:by_goal:{goal.id}"
    assert body["active"]["id"] == f"template:by_goal:{goal.id}"

    # Cache is keyed by goal_id: a section cached for this goal is invisible to a different goal.
    other_goal = await create_goal(organization_id=user.organization_id, owner_id=user.id, creator_id=user.id)
    identifier = MailboxViewIdentifier.for_template("by_goal", goal_id=goal.id)
    assert identifier is not None
    await identifier.write_cache(user.id, [{"title": "", "mailbox_entry_ids": []}])

    this_goal = (await client.get(f"/api/mailbox_views?template=by_goal&goal_id={goal.id}")).json()
    assert this_goal["cached_sections"] is not None
    other = (await client.get(f"/api/mailbox_views?template=by_goal&goal_id={other_goal.id}")).json()
    assert other["cached_sections"] is None


@pytest.mark.asyncio
async def test_by_goal_validates_goal(client: AppClient):
    user = await client.get_default_user()
    # Missing goal_id is semantically invalid for the by_goal sort.
    missing = await client.get("/api/mailbox_views?template=by_goal")
    assert missing.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Foreign-org goal → 404 (org-scoped; never leak existence via 403).
    stranger = await create_user()
    foreign_goal = await create_goal(
        organization_id=stranger.organization_id, owner_id=stranger.id, creator_id=stranger.id
    )
    foreign = await client.get(f"/api/mailbox_views?template=by_goal&goal_id={foreign_goal.id}")
    assert foreign.status_code == status.HTTP_404_NOT_FOUND

    # Owned-but-closed goal → 422.
    closed_goal = await create_goal(
        organization_id=user.organization_id,
        owner_id=user.id,
        creator_id=user.id,
        closed_at=datetime.now(UTC),
    )
    closed = await client.get(f"/api/mailbox_views?template=by_goal&goal_id={closed_goal.id}")
    assert closed.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
