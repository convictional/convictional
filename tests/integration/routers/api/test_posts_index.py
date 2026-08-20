from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import status

from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Collaborator, LinkPreview, SubscriptionPreference, Visit
from app.models.workspaces.posts import Post, PostComment
from config.enums import CollaboratorStatus, EventAction, LinkPreviewStatus, Sharing, SubscriptionLevel
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_attachment,
    create_decision,
    create_group,
    create_organization,
    create_post,
    create_post_comment,
    create_user,
)


@pytest.mark.asyncio
async def test_list_envelope_filters_and_pinned(client: AppClient):
    creator = await client.get_default_user()
    org_id = creator.organization_id
    group = await create_group(organization_id=org_id, name="Engineering")

    await create_post(creator_id=creator.id, organization_id=org_id, group_id=group.id, title="Grouped Post")
    decided = await create_post(creator_id=creator.id, organization_id=org_id, title="Decided Post")
    decision_comment = await create_post_comment(post_id=decided.id, user_id=creator.id, content="We decided this")
    await create_decision(workspace_id=decided.workspace_id, comment=decision_comment, decided_by_id=creator.id)
    await create_post(creator_id=creator.id, organization_id=org_id, title="Open Post")
    pinned = await create_post(creator_id=creator.id, organization_id=org_id, title="Pinned Post")
    await pinned.pin()
    await create_post(creator_id=creator.id, organization_id=org_id, title="My Draft", published_at=None)

    # Default list: `posts` + the draft_count badge. With no pinned filter, pinned
    # posts appear inline; drafts never do (they have their own endpoint).
    response = await client.get("/api/posts")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert set(body) == {"posts", "decisions", "draft_count", "next_cursor", "has_more"}
    assert body["has_more"] is False
    assert body["next_cursor"] is None
    assert body["draft_count"] == 1
    main_titles = {p["title"] for p in body["posts"]}
    assert main_titles == {"Grouped Post", "Decided Post", "Open Post", "Pinned Post"}
    assert "My Draft" not in main_titles  # drafts never appear in the published list

    # The decision badge is sourced from the sparse `decisions` envelope (keyed by
    # post_id), not from PostResponse — only decided posts appear there.
    decisions = {d["post_id"]: d for d in body["decisions"]}
    assert decisions[str(decided.id)]["count"] == 1
    assert decisions[str(decided.id)]["comment_preview"] == "We decided this"
    assert str(pinned.id) not in decisions

    decided_card = next(p for p in body["posts"] if p["title"] == "Decided Post")
    assert decided_card["creator"]["id"] == str(creator.id)

    # The list returns the canonical PostResponse (same shape as GET /api/posts/{id}),
    # so it carries the detail fields — permissions, workspace_id, pin/announce state.
    assert decided_card["permissions"] == {"edit": True, "pin": False, "delete": True}
    assert decided_card["workspace_id"]
    assert decided_card["is_pinned"] is False
    assert decided_card["is_announcement"] is False

    # pinned is a filter: ?pinned=true is the rail, ?pinned=false the feed body.
    response = await client.get("/api/posts?pinned=true")
    assert {p["title"] for p in response.json()["posts"]} == {"Pinned Post"}
    response = await client.get("/api/posts?pinned=false")
    assert {p["title"] for p in response.json()["posts"]} == {"Grouped Post", "Decided Post", "Open Post"}

    # group_id filter.
    response = await client.get(f"/api/posts?group_id={group.id}")
    assert {p["title"] for p in response.json()["posts"]} == {"Grouped Post"}

    # decided filter.
    response = await client.get("/api/posts?decided=true")
    assert {p["title"] for p in response.json()["posts"]} == {"Decided Post"}


@pytest.mark.asyncio
async def test_drafts_collection(client: AppClient):
    creator = await client.get_default_user()
    org_id = creator.organization_id
    other = await create_user(organization_id=org_id)

    await create_post(creator_id=creator.id, organization_id=org_id, title="Published Post")
    await create_post(creator_id=creator.id, organization_id=org_id, title="My Draft", published_at=None)
    # A draft owned by someone else, no shared visibility → not in creator's drafts.
    await create_post(creator_id=other.id, organization_id=org_id, title="Other Draft", published_at=None)

    # GET /api/posts/drafts is its own paginated collection: just `drafts` + cursor.
    response = await client.get("/api/posts/drafts")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert set(body) == {"drafts", "next_cursor", "has_more"}
    assert {d["title"] for d in body["drafts"]} == {"My Draft"}
    draft_card = body["drafts"][0]
    assert set(draft_card) == {"id", "title", "creator", "collaborators", "updated_at"}
    assert {c["id"] for c in draft_card["collaborators"]} == {str(creator.id)}

    # The published list never contains drafts (there is no status filter here).
    response = await client.get("/api/posts")
    assert "My Draft" not in {p["title"] for p in response.json()["posts"]}


@pytest.mark.asyncio
async def test_drafts_visibility_tracks_collaborators(client: AppClient):
    # Drafts surface to their creator and to active workspace collaborators; the
    # draft_count badge counts each visible draft once even with multiple
    # collaborators (regression for COUNT(*) vs COUNT(DISTINCT id) across the JOIN).
    creator = await client.get_default_user()
    org_id = creator.organization_id
    collaborator = await create_user(organization_id=org_id)

    await create_post(creator_id=creator.id, organization_id=org_id, title="Solo Draft", published_at=None)
    shared_draft = await create_post(
        creator_id=creator.id, organization_id=org_id, title="Shared Draft", published_at=None
    )
    await Collaborator.create(workspace_id=shared_draft.workspace_id, user_id=collaborator.id)

    async def draft_titles() -> set[str]:
        response = await client.get("/api/posts/drafts")
        assert response.status_code == status.HTTP_200_OK
        return {d["title"] for d in response.json()["drafts"]}

    async def draft_count() -> int:
        response = await client.get("/api/posts")
        assert response.status_code == status.HTTP_200_OK
        return response.json()["draft_count"]

    # Creator sees both drafts; the badge counts both once.
    assert await draft_titles() == {"Solo Draft", "Shared Draft"}
    assert await draft_count() == 2

    # The collaborator sees only the shared draft.
    with client.current_user_as(collaborator):
        assert await draft_titles() == {"Shared Draft"}

    # A second collaborator stresses the JOIN dedup — the creator's count stays 2.
    third_user = await create_user(organization_id=org_id)
    await Collaborator.create(workspace_id=shared_draft.workspace_id, user_id=third_user.id)
    assert await draft_count() == 2

    # A pending collaborator does not gain visibility.
    pending_user = await create_user(organization_id=org_id)
    await Collaborator.create(
        workspace_id=shared_draft.workspace_id, user_id=pending_user.id, status=CollaboratorStatus.PENDING
    )
    with client.current_user_as(pending_user):
        assert "Shared Draft" not in await draft_titles()

    # Removing a collaborator revokes visibility.
    await Collaborator.filter(workspace_id=shared_draft.workspace_id, user_id=collaborator.id).delete()
    with client.current_user_as(collaborator):
        assert "Shared Draft" not in await draft_titles()


@pytest.mark.asyncio
async def test_list_pagination_and_first_page_only_extras(client: AppClient):
    creator = await client.get_default_user()
    org_id = creator.organization_id
    for i in range(31):
        await create_post(creator_id=creator.id, organization_id=org_id, title=f"Post {i:02d}")
    await create_post(creator_id=creator.id, organization_id=org_id, title="A Draft", published_at=None)

    response = await client.get("/api/posts")
    body = response.json()
    assert len(body["posts"]) == 30
    assert body["has_more"] is True
    assert body["next_cursor"] is not None
    assert body["draft_count"] == 1

    # Cursor page returns the remainder; draft_count is first-page-only.
    response = await client.get(f"/api/posts?cursor={body['next_cursor']}")
    body = response.json()
    assert len(body["posts"]) == 1
    assert body["has_more"] is False
    assert body["draft_count"] == 0

    # An empty cursor is the first page (matches Pagination's own truthiness test):
    # it must still carry draft_count, not be treated as a later page.
    response = await client.get("/api/posts?cursor=")
    body = response.json()
    assert len(body["posts"]) == 30
    assert body["draft_count"] == 1


@pytest.mark.asyncio
async def test_list_ignores_free_text_query_param(client: AppClient):
    # Search is served by GET /api/search?content_type=post, not here. A stray ?q= is
    # an undeclared param and is ignored — the normal filtered list comes back.
    user = await client.get_default_user()
    org_id = user.organization_id
    await create_post(creator_id=user.id, organization_id=org_id, title="Quarterly budget planning")
    await create_post(creator_id=user.id, organization_id=org_id, title="Unrelated frontend refactor")

    response = await client.get("/api/posts?q=budget")
    assert response.status_code == status.HTTP_200_OK
    titles = {p["title"] for p in response.json()["posts"]}
    assert titles == {"Quarterly budget planning", "Unrelated frontend refactor"}


@pytest.mark.asyncio
async def test_new_comment_count_semantics(client: AppClient):
    creator = await client.get_default_user()
    org_id = creator.organization_id
    other = await create_user(organization_id=org_id)
    post = await create_post(creator_id=creator.id, organization_id=org_id, title="Discussion")

    # Visit recorded an hour ago; comments below are created "now" → after the visit.
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    await Visit.create(user_id=creator.id, workspace_id=post.workspace_id)
    await Visit.filter(user_id=creator.id, workspace_id=post.workspace_id).update(updated_at=one_hour_ago)

    # Another user's comment counts; the viewer's own comment does not; the
    # original comment is always excluded.
    await create_post_comment(post_id=post.id, user_id=other.id, content="From someone else")
    await create_post_comment(post_id=post.id, user_id=creator.id, content="My own reply")

    def card_for(body, title):
        return next(p for p in body["posts"] if p["title"] == title)

    response = await client.get("/api/posts")
    card = card_for(response.json(), "Discussion")
    # 3 comments total (original + two), only the other user's counts as new.
    assert card["comment_count"] == 2
    assert card["new_comment_count"] == 1

    # A decision by another user adds +1.
    decision_comment = await create_post_comment(post_id=post.id, user_id=other.id, content="Decision text")
    await create_decision(workspace_id=post.workspace_id, comment=decision_comment, decided_by_id=other.id)
    response = await client.get("/api/posts")
    card = card_for(response.json(), "Discussion")
    assert card["new_comment_count"] == 3  # two other-user comments + 1 decision

    # Caught up: a fresh visit (now) means nothing is new.
    await Visit.filter(user_id=creator.id, workspace_id=post.workspace_id).update(updated_at=datetime.now(UTC))
    response = await client.get("/api/posts")
    card = card_for(response.json(), "Discussion")
    assert card["new_comment_count"] == 0


@pytest.mark.asyncio
async def test_card_link_preview_ready_gated(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, title="With Preview")
    link_preview = await LinkPreview.create(
        url="https://example.com/article",
        url_hash="hash-ready-preview",
        status=LinkPreviewStatus.READY,
        title="Article Title",
        image_url="https://example.com/img.png",
    )
    original = await PostComment.get(post_id=post.id)
    await PostComment.filter(id=original.id).update(link_preview_id=link_preview.id)

    response = await client.get("/api/posts")
    card = next(p for p in response.json()["posts"] if p["title"] == "With Preview")
    assert card["link_preview"] is not None
    assert card["link_preview"]["title"] == "Article Title"


@pytest.mark.asyncio
async def test_create_post_link_preview_unfurl(client: AppClient):
    await client.get_default_user()

    # A URL in the body is unfurled at create and the preview is associated.
    response = await client.post(
        "/api/posts",
        json={"title": "Check this out", "content": "Look at https://github.com/anthropics/claude-code"},
    )
    assert response.status_code == status.HTTP_201_CREATED

    post = await Post.first().prefetch_related("comments")
    assert post is not None
    comment = post.original_comment
    await comment.refresh_from_db()
    assert comment.link_preview_id is not None
    link_preview = await LinkPreview.get(id=comment.link_preview_id)
    assert link_preview.status == LinkPreviewStatus.READY

    # unfurl_links=false skips association. This is the React composer's documented
    # parity: unfurl is server-side at submit, with no per-post opt-out beyond the flag.
    response = await client.post(
        "/api/posts",
        json={
            "title": "No card please",
            "content": "Look at https://github.com/anthropics/claude-code",
            "unfurl_links": False,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    new_post = await Post.all().order_by("-created_at").first()
    assert new_post is not None
    new_comment = await new_post.comments.all().first()
    assert new_comment is not None
    assert new_comment.link_preview_id is None


@pytest.mark.asyncio
async def test_create_post_publishes_with_side_effects(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    mentioned = await create_user(organization_id=creator.organization_id, name="Mentioned User")
    group = await create_group(organization_id=creator.organization_id)

    # An unclaimed attachment (no workspace yet — the post is created after upload),
    # carrying the claim_id the composer sends.
    claim_id = uuid4()
    attachment = await create_attachment(
        workspace_id=None, claim_id=claim_id, user_id=creator.id, filename="doc.png", content=b"data"
    )

    # Two URLs in the body — only the first is unfurled, so exactly one preview lands.
    response = await client.post(
        "/api/posts",
        json={
            "title": "Launch Plan",
            "content": (
                f"Hey @[{mentioned.display_name}], see https://github.com/anthropics/claude-code "
                "and https://github.com/anthropics/courses"
            ),
            "group_id": str(group.id),
            "attachment_claim_id": str(claim_id),
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    card = response.json()
    assert card["title"] == "Launch Plan"
    assert card["creator"]["id"] == str(creator.id)

    post = await Post.get(id=card["id"]).prefetch_related("comments")
    assert post.is_published
    assert post.group_id == group.id
    comment = post.original_comment
    assert comment is not None

    # Mention resolved → collaborator added.
    collaborator = await Collaborator.get_or_none(workspace_id=post.workspace_id, user_id=mentioned.id)
    assert collaborator is not None

    # Only the first URL is unfurled; the preview + attachment land on the comment.
    await comment.refresh_from_db()
    assert comment.link_preview_id is not None
    assert await LinkPreview.all().count() == 1
    await attachment.refresh_from_db()
    assert attachment.claim_id is None
    assert attachment.workspace_id == post.workspace_id

    # A teammate can download the now-claimed attachment.
    teammate = await create_user(organization_id=creator.organization_id)
    with client.current_user_as(teammate):
        response = await client.get(f"/workspaces/attachments/{attachment.id}/download", follow_redirects=False)
        assert response.status_code == status.HTTP_302_FOUND


@pytest.mark.asyncio
async def test_create_post_announcement_admin_gated(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()

    # Non-admin announcement is silently downgraded.
    response = await client.post(
        "/api/posts", json={"title": "Sneaky", "content": "Trying to announce", "is_announcement": True}
    )
    assert response.status_code == status.HTTP_201_CREATED
    post = await Post.get(id=response.json()["id"])
    assert post.is_announcement is False

    # Admin announcement sticks, clears the group, and notifies the whole org — even
    # a member who isn't subscribed gets an inbox entry.
    admin = await create_user(organization_id=creator.organization_id, is_admin=True)
    member = await create_user(organization_id=creator.organization_id, last_logged_in_at=datetime.now(UTC))
    group = await create_group(organization_id=creator.organization_id)
    with client.current_user_as(admin):
        response = await client.post(
            "/api/posts",
            json={
                "title": "Company Update",
                "content": "Big news",
                "is_announcement": True,
                "group_id": str(group.id),
            },
        )
    assert response.status_code == status.HTTP_201_CREATED
    announced = await Post.get(id=response.json()["id"])
    assert announced.is_announcement is True
    assert announced.group_id is None

    await announced.fetch_related("workspace__events")
    assert EventAction.POST_ANNOUNCED in [event.action for event in announced.workspace.events]
    entry = await MailboxEntry.filter(owner_id=member.id, resource_gid=str(announced.global_id)).first()
    assert entry is not None
    assert entry.is_inbox


@pytest.mark.asyncio
async def test_announcement_reaches_relevant_only_member_but_regular_post_does_not(
    client: AppClient, background_jobs: InlineJobs
):
    # An announcement is "sent to everyone, even if unsubscribed": a member who lowered their
    # Post preference to RELEVANT_ONLY still gets it in their inbox. An ordinary org-wide post
    # stays tier-gated and does NOT reach that member.
    admin = await client.get_default_user()
    await admin.make_admin()
    member = await create_user(organization_id=admin.organization_id, last_logged_in_at=datetime.now(UTC))
    await SubscriptionPreference.update_for(member.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})

    announcement = await client.post(
        "/api/posts", json={"title": "All hands", "content": "Everyone read this", "is_announcement": True}
    )
    assert announcement.status_code == status.HTTP_201_CREATED
    announced = await Post.get(id=announcement.json()["id"])
    announcement_entry = await MailboxEntry.filter(owner_id=member.id, resource_gid=str(announced.global_id)).first()
    assert announcement_entry is not None
    assert announcement_entry.is_inbox

    # Reach comes from org-accessor resolution: the member who received it was never added as a
    # collaborator, and no per-member collaborator rows are written for the announcement (only the
    # creator's row exists).
    assert not await Collaborator.filter(workspace_id=announced.workspace_id, user_id=member.id).exists()
    assert await Collaborator.filter(workspace_id=announced.workspace_id).count() == 1

    regular = await client.post("/api/posts", json={"title": "Just a post", "content": "nothing urgent"})
    assert regular.status_code == status.HTTP_201_CREATED
    regular_post = await Post.get(id=regular.json()["id"])
    regular_entry = await MailboxEntry.filter(owner_id=member.id, resource_gid=str(regular_post.global_id)).first()
    assert regular_entry is None


@pytest.mark.asyncio
async def test_announcement_excludes_deleted_and_never_logged_in_members(
    client: AppClient, background_jobs: InlineJobs
):
    # The force-include path reaches org accessors but must not surface an announcement to accounts
    # that can't legitimately receive it. Both members are RELEVANT_ONLY so the ALL-tier path can't
    # reach them independently — this isolates the force-include guards.
    admin = await client.get_default_user()
    await admin.make_admin()

    deleted_member = await create_user(organization_id=admin.organization_id, last_logged_in_at=datetime.now(UTC))
    never_logged_in = await create_user(organization_id=admin.organization_id, last_logged_in_at=None)
    for member in (deleted_member, never_logged_in):
        await SubscriptionPreference.update_for(member.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})
    await deleted_member.soft_delete()

    announcement = await client.post(
        "/api/posts", json={"title": "All hands", "content": "Everyone read this", "is_announcement": True}
    )
    assert announcement.status_code == status.HTTP_201_CREATED
    announced = await Post.get(id=announcement.json()["id"])

    for member in (deleted_member, never_logged_in):
        entry = await MailboxEntry.filter(owner_id=member.id, resource_gid=str(announced.global_id)).first()
        assert entry is None


@pytest.mark.asyncio
async def test_comment_on_announcement_does_not_realert_relevant_only_member(
    client: AppClient, background_jobs: InlineJobs
):
    # Force-include is scoped to the announce event, not every event on the post. So a RELEVANT_ONLY
    # member gets the announcement once, but a later comment by someone else does NOT re-surface it
    # as unread — being dragged back into the thread would contradict the "relevant only" promise.
    # (A BROADCASTS/ALL member would still be re-alerted via normal tier rules; RELEVANT_ONLY is
    # only pulled in by an @mention or a reply to them.)
    admin = await client.get_default_user()
    await admin.make_admin()
    member = await create_user(organization_id=admin.organization_id, last_logged_in_at=datetime.now(UTC))
    await SubscriptionPreference.update_for(member.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})

    announcement = await client.post(
        "/api/posts", json={"title": "All hands", "content": "Kickoff", "is_announcement": True}
    )
    announced = await Post.get(id=announcement.json()["id"])

    # The announce event reached them; mark it read so a re-alert would be observable.
    entry = await MailboxEntry.filter(owner_id=member.id, resource_gid=str(announced.global_id)).first()
    assert entry is not None and entry.is_inbox
    await entry.mark_as_read()

    comment = await client.post(f"/api/posts/{announced.id}/comments", json={"content": "a follow-up"})
    assert comment.status_code == status.HTTP_201_CREATED

    await entry.refresh_from_db()
    assert not entry.is_unread  # a stranger's comment did not re-surface it
    # Reach never depended on a collaborator row.
    assert not await Collaborator.filter(workspace_id=announced.workspace_id, user_id=member.id).exists()


@pytest.mark.asyncio
async def test_create_draft_is_distinct_blank_tolerant_flow(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    group = await create_group(organization_id=creator.organization_id)

    # Blank title/content accepted; carries group + is_announcement (non-admin
    # downgrade applies); creates a LiveDocument, not a PostComment; no Notifier.
    response = await client.post(
        "/api/posts/drafts",
        json={"title": "", "content": "", "group_id": str(group.id), "is_announcement": True},
    )
    assert response.status_code == status.HTTP_201_CREATED
    card = response.json()
    assert card["title"] == "Untitled draft"

    draft = await Post.get(id=card["id"]).prefetch_related("comments")
    assert draft.is_draft
    assert draft.sharing == Sharing.PRIVATE
    assert draft.group_id == group.id  # non-admin → announcement downgraded, group kept
    assert draft.is_announcement is False
    assert len(draft.comments) == 0

    # A draft with content stores it as a LiveDocument (no comment row).
    response = await client.post("/api/posts/drafts", json={"title": "Draft Two", "content": "Some body"})
    assert response.status_code == status.HTTP_201_CREATED
    draft2 = await Post.get(id=response.json()["id"]).prefetch_related("comments")
    assert len(draft2.comments) == 0
    live_doc = await LiveDocument.for_topic(draft2.live_document_topic)
    assert (live_doc.markdown or "").strip() == "Some body"

    # Drafts don't appear in the default (open) list.
    response = await client.get("/api/posts")
    titles = {p["title"] for p in response.json()["posts"]}
    assert "Untitled draft" not in titles and "Draft Two" not in titles


@pytest.mark.asyncio
async def test_create_rejects_cross_org_group(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    foreign_group = await create_group(organization_id=(await create_organization()).id)

    # A group from another org would pull its members onto the post's workspace via
    # the post-save collaborator signal — both create paths reject it (422).
    response = await client.post("/api/posts", json={"title": "X", "content": "Y", "group_id": str(foreign_group.id)})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    response = await client.post("/api/posts/drafts", json={"group_id": str(foreign_group.id)})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # A group from the user's own org is accepted.
    own_group = await create_group(organization_id=creator.organization_id)
    response = await client.post("/api/posts", json={"title": "X", "content": "Y", "group_id": str(own_group.id)})
    assert response.status_code == status.HTTP_201_CREATED
