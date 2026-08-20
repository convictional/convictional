import pytest

from app.models.collaboration.workspace import CommentReaction
from app.models.workspaces.email.thread import EmailThreadComment
from app.presenters.comment import CommentPresenter
from config.enums import ReactionType
from tests.helpers.factories import create_email_thread, create_user


@pytest.mark.asyncio
async def test_comment_presenter_lists():
    thread = await create_email_thread()
    commenter = await create_user(organization_id=thread.organization_id)

    reactive_user_1 = await create_user(organization_id=thread.organization_id)
    reactive_user_2 = await create_user(organization_id=thread.organization_id)
    reactive_user_3 = await create_user(organization_id=thread.organization_id)

    comment_1 = EmailThreadComment(
        email_thread_id=thread.id,
        user_id=commenter.id,
        reactions={ReactionType.THUMBS_UP.value: [reactive_user_1.id, reactive_user_2.id]},
    )
    await comment_1.save()

    comment_2 = EmailThreadComment(
        email_thread_id=thread.id,
        user_id=commenter.id,
        reactions={ReactionType.THUMBS_UP.value: [reactive_user_1.id, reactive_user_3.id]},
    )
    await comment_2.save()

    thumbs_up_reaction = CommentReaction.by_type(ReactionType.THUMBS_UP)
    presenters = await CommentPresenter.create_from_list([comment_1, comment_2])
    assert len(presenters) == 2

    assert presenters[0].model == comment_1
    assert len(presenters[0].reaction_users) == 2
    assert reactive_user_1 in presenters[0].reactions_with_users[thumbs_up_reaction]
    assert reactive_user_2 in presenters[0].reactions_with_users[thumbs_up_reaction]

    assert presenters[1].model == comment_2
    assert len(presenters[1].reaction_users) == 2
    assert reactive_user_1 in presenters[1].reactions_with_users[thumbs_up_reaction]
    assert reactive_user_3 in presenters[1].reactions_with_users[thumbs_up_reaction]
