import pytest
from fastapi import status

from app.models.workspaces.documents import DocumentComment
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_document,
    create_email_contact,
    create_email_thread,
    create_email_thread_comment,
    create_goal,
    create_post,
    create_post_comment,
)


@pytest.mark.asyncio
async def test_gid_routing(client: AppClient):
    user = await client.get_default_user()
    # Post Comments
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    post_comment = await create_post_comment(user_id=user.id, post_id=post.id)

    post_router_response = await client.get(f"/posts/{post.id}")
    assert post_router_response.status_code == status.HTTP_200_OK

    gid_router_response = await client.get(f"/gid/{post_comment.global_id.to_param}")
    assert gid_router_response.status_code == status.HTTP_200_OK
    post_comment_url = f"{post_router_response.url}#comment-{post_comment.id}"
    assert post_comment_url == gid_router_response.url

    # Goals
    goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)

    goals_router_response = await client.get("/goals")
    assert goals_router_response.status_code == status.HTTP_200_OK

    gid_router_response = await client.get(f"/gid/{goal.global_id.to_param}")
    assert gid_router_response.status_code == status.HTTP_200_OK
    goal_url = f"{goals_router_response.url}#goal-{goal.id}"
    assert goal_url == gid_router_response.url

    goal.planning_list_name = "test list"
    await goal.save()

    gid_router_response = await client.get(f"/gid/{goal.global_id.to_param}")
    assert gid_router_response.status_code == status.HTTP_200_OK
    goal_url = f"{goals_router_response.url}?planning_list_name=test+list#goal-{goal.id}"
    assert goal_url == gid_router_response.url

    # Documents
    document = await create_document(creator_id=user.id, organization_id=user.organization_id)
    document_response = await client.get(f"/documents/{document.id}")
    assert document_response.status_code == status.HTTP_200_OK

    gid_router_response = await client.get(f"/gid/{document.global_id.to_param}")
    assert gid_router_response.status_code == status.HTTP_200_OK
    assert document_response.url == gid_router_response.url

    # Document Comments deep-link into the editor (comments are edited there),
    # not the read-only show page the bare Document gid resolves to above.
    document_comment = await DocumentComment.create(
        document_id=document.id, user_id=user.id, content="test", quoted_text="text", comment_mark_id="mark-1"
    )
    gid_router_response = await client.get(f"/gid/{document_comment.global_id.to_param}")
    assert gid_router_response.status_code == status.HTTP_200_OK
    assert str(gid_router_response.url).endswith(f"/documents/{document.id}/edit#comment-{document_comment.id}")

    # Email-thread comments delegate to the thread URL but must keep the `#comment-<id>`
    # fragment so the thread island deep-links to the comment instead of the thread top.
    email_thread = await create_email_thread(organization_id=user.organization_id, creator_id=user.id)
    thread_comment = await create_email_thread_comment(
        workspace_id=email_thread.workspace_id, organization_id=user.organization_id, user_id=user.id
    )
    gid_router_response = await client.get(f"/gid/{thread_comment.global_id.to_param}")
    assert gid_router_response.status_code == status.HTTP_200_OK
    assert str(gid_router_response.url).endswith(f"/email_threads/{email_thread.id}#comment-{thread_comment.id}")


@pytest.mark.asyncio
async def test_gid_routing_preserves_query_params(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    gid_response = await client.get(f"/gid/{post.global_id.to_param}?foo=bar", follow_redirects=False)
    assert gid_response.status_code == status.HTTP_303_SEE_OTHER
    assert gid_response.headers["location"].endswith(f"/posts/{post.id}?foo=bar")

    # Query params should appear before fragments
    goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)
    gid_response = await client.get(f"/gid/{goal.global_id.to_param}?foo=bar", follow_redirects=False)
    assert gid_response.status_code == status.HTTP_303_SEE_OTHER
    assert f"?foo=bar#goal-{goal.id}" in gid_response.headers["location"]


@pytest.mark.asyncio
async def test_gid_redirect_unmapped_type_returns_404(client: AppClient):
    user = await client.get_default_user()
    # Uses a real EmailContact record so the 404 comes from the unmapped-type path
    # (get_workspace_url returns None for EmailContact), not from DoesNotExist.
    contact = await create_email_contact(organization_id=user.organization_id, user_id=user.id)

    response = await client.get(f"/gid/{contact.global_id.to_param}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
