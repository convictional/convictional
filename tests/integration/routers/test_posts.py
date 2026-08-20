import pytest
from fastapi import status

from app.models.collaboration.content import Content
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import SubscriptionPreference
from app.models.workspaces.posts import Post, PostMailboxEntry
from config.enums import (
    ContentType,
    Sharing,
    SubscriptionLevel,
)
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_collaborator,
    create_post,
    create_user,
)


@pytest.mark.asyncio
async def test_managing_posts(client: AppClient):
    user = await client.get_default_user()

    # Test creation
    response = await client.post("/api/posts", json={"title": "Lunch", "content": "What should we eat for lunch?"})
    assert response.status_code == status.HTTP_201_CREATED

    assert await Post.all().count() == 1
    post = await Post.first().prefetch_related("workspace__collaborators", "comments")
    assert isinstance(post, Post)
    assert len(post.comments) == 1
    assert post.title == "Lunch"
    assert post.creator_id == user.id
    assert post.original_comment.content == "What should we eat for lunch?"
    assert post.original_comment.user_id == user.id

    assert post.sharing == Sharing.ORGANIZATION
    assert len(post.workspace.collaborators) == 1
    assert post.workspace.collaborators[0].user_id == user.id
    assert not (await post.workspace.subscription_for(user.id)).wants_all

    assert await Content.all().count() == 2
    post_content = await Content.filter(content_type=ContentType.POST).first()
    assert post_content is not None
    assert post_content.source_id == str(post.global_id)
    assert post_content.title is not None
    assert post_content.index_content is not None
    comment_content = await Content.filter(content_type=ContentType.POST_COMMENT).first()
    assert comment_content is not None
    assert comment_content.source_id == str(post.original_comment.global_id)
    assert comment_content.title is not None
    assert comment_content.index_content is not None

    # The show page (/posts/{id}) is now served by the SPA shell — covered in
    # test_spa.py. The body/comments come from GET /api/posts/{id}; post body
    # editing lives on PATCH /api/posts/{id} (see test_posts_api.py).

    # Test deletion (now via the JSON API — see test_posts_api.py for permissions)
    response = await client.delete(f"/api/posts/{post.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    assert await Post.all().count() == 0
    assert await Post.deleted.get_queryset().count() == 1
    assert await Content.all().count() == 0


@pytest.mark.asyncio
async def test_deleting_post_cleans_up_mailbox_entries(client: AppClient):
    creator = await client.get_default_user()
    subscriber = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(creator.id, {Post.record_type: SubscriptionLevel.ALL})

    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, title="Post To Delete")
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, user_id=subscriber.id)
    await post.workspace.subscribe(subscriber.id)

    await PostMailboxEntry(post).sync()

    # Verify MailboxEntries exist for both creator and subscriber
    entries_before = await MailboxEntry.filter(MailboxEntry.filters.by_resource(post.global_id)).all()
    owner_ids = {entry.owner_id for entry in entries_before}
    assert creator.id in owner_ids
    assert subscriber.id in owner_ids
    assert all(not entry.is_deleted for entry in entries_before)

    # Delete the post via the JSON API
    response = await client.delete(f"/api/posts/{post.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify the post is soft-deleted
    await post.refresh_from_db()
    assert post.is_deleted

    # All MailboxEntries for this post should be soft-deleted
    entries_after = await MailboxEntry.unscoped.filter(MailboxEntry.filters.by_resource(post.global_id)).all()
    assert len(entries_after) > 0
    assert all(entry.is_deleted for entry in entries_after)
