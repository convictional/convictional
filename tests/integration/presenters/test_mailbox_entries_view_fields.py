import pytest

from app.presenters.mailbox_entries import MailboxEntryPresenter
from tests.helpers.factories import (
    create_chat,
    create_chat_message,
    create_collaborator,
    create_email_thread,
    create_group,
    create_mailbox_entry,
    create_post,
    create_post_comment,
    create_user,
)


async def _present(entry, email):
    presenters = await MailboxEntryPresenter.create_from_list([entry], email)
    return presenters[0]


@pytest.mark.asyncio
async def test_view_fields_for_post():
    user = await create_user()
    group = await create_group(organization_id=user.organization_id, name="Engineering")
    post = await create_post(
        organization_id=user.organization_id, creator_id=user.id, group_id=group.id, title="Q3 roadmap"
    )
    entry = await create_mailbox_entry(
        owner_id=user.id,
        organization_id=user.organization_id,
        resource_gid=post.global_id,
        title="Q3 roadmap",
    )

    presenter = await _present(entry, user.email)

    assert presenter.item_type == "Post"
    assert presenter.author_name == user.display_name
    assert presenter.audience == "Engineering"


@pytest.mark.asyncio
async def test_view_fields_for_org_wide_post():
    user = await create_user()
    post = await create_post(organization_id=user.organization_id, creator_id=user.id, title="All hands")
    entry = await create_mailbox_entry(
        owner_id=user.id, organization_id=user.organization_id, resource_gid=post.global_id, title="All hands"
    )

    presenter = await _present(entry, user.email)

    assert presenter.item_type == "Post"
    assert presenter.audience == "Whole organization"


@pytest.mark.asyncio
async def test_view_fields_for_group_chat():
    user = await create_user()
    speaker = await create_user(organization_id=user.organization_id)
    group = await create_group(organization_id=user.organization_id, name="GTM")
    chat = await create_chat(organization_id=user.organization_id, creator_id=user.id, group_id=group.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=speaker.id, organization_id=user.organization_id)
    await create_chat_message(chat_id=chat.id, user_id=speaker.id, content="Latest update")

    entry = await create_mailbox_entry(
        owner_id=user.id,
        organization_id=user.organization_id,
        resource_gid=chat.global_id,
        title="GTM",
    )

    presenter = await _present(entry, user.email)

    assert presenter.item_type == "Chat"
    assert presenter.author_name == speaker.display_name
    assert presenter.audience == "GTM"


@pytest.mark.asyncio
async def test_audience_group_chat_falls_back_when_group_missing():
    # A group chat whose group row is unavailable (deleted, or not prefetched) while the FK id is
    # still set must read as a group, not fall through to enumerating every collaborator under a
    # "Chat with …" label.
    user = await create_user()
    group = await create_group(organization_id=user.organization_id, name="GTM")
    chat = await create_chat(organization_id=user.organization_id, creator_id=user.id, group_id=group.id)
    entry = await create_mailbox_entry(
        owner_id=user.id, organization_id=user.organization_id, resource_gid=chat.global_id, title="GTM"
    )

    presenter = await _present(entry, user.email)
    # Drop the related group object while keeping the FK id set, mimicking a deleted/unfetched group.
    presenter.resource.group = None
    presenter.resource.group_id = group.id

    assert presenter.is_group_chat is True
    assert presenter.audience == "Group chat"


@pytest.mark.asyncio
async def test_view_fields_for_email():
    user = await create_user()
    thread = await create_email_thread(organization_id=user.organization_id)
    entry = await create_mailbox_entry(
        owner_id=user.id, organization_id=user.organization_id, resource_gid=thread.global_id
    )

    presenter = await _present(entry, user.email)

    assert presenter.item_type == "Email"


@pytest.mark.asyncio
async def test_body_preview_surfaces_body_per_resource_type():
    # Each resource type stashes its body in a different place. Emails denormalize a snippet into the
    # entry's `preview`; chats denormalize the last message into `last_comment`; posts leave both
    # empty and keep the body in the post's first comment. body_preview must surface real content for
    # all three so the LLM never scores a post or chat on its bare title (the email-shaped `preview`
    # column was rendering blank for posts and chats).
    user = await create_user()

    thread = await create_email_thread(organization_id=user.organization_id)
    email_entry = await create_mailbox_entry(
        owner_id=user.id,
        organization_id=user.organization_id,
        resource_gid=thread.global_id,
        preview="Quarterly numbers attached",
        last_comment="",
    )

    chat = await create_chat(organization_id=user.organization_id, creator_id=user.id)
    await create_chat_message(chat_id=chat.id, user_id=user.id, content="Standup notes are up")
    chat_entry = await create_mailbox_entry(
        owner_id=user.id,
        organization_id=user.organization_id,
        resource_gid=chat.global_id,
        preview="",
        last_comment="Standup notes are up",
    )

    # Unpublished so create_post seeds no default comment; the explicit one is then the body.
    post = await create_post(
        organization_id=user.organization_id, creator_id=user.id, title="Q3 roadmap", published_at=None
    )
    await create_post_comment(post_id=post.id, user_id=user.id, content="Ship the Q3 roadmap — scope inside.")
    post_entry = await create_mailbox_entry(
        owner_id=user.id,
        organization_id=user.organization_id,
        resource_gid=post.global_id,
        preview="",
        last_comment="",
    )

    # A post with no comments falls back to the entry's columns rather than erroring.
    empty_post = await create_post(
        organization_id=user.organization_id, creator_id=user.id, title="Silent", published_at=None
    )
    empty_post_entry = await create_mailbox_entry(
        owner_id=user.id,
        organization_id=user.organization_id,
        resource_gid=empty_post.global_id,
        preview="",
        last_comment="fallback text",
    )

    presenters = await MailboxEntryPresenter.create_from_list(
        [email_entry, chat_entry, post_entry, empty_post_entry], user.email, include_body=True
    )
    by_id = {p.model.id: p for p in presenters}

    assert by_id[email_entry.id].body_preview == "Quarterly numbers attached"
    assert by_id[chat_entry.id].body_preview == "Standup notes are up"
    assert by_id[post_entry.id].body_preview == "Ship the Q3 roadmap — scope inside."
    assert by_id[empty_post_entry.id].body_preview == "fallback text"
