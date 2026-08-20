import re
from typing import TypeVar
from uuid import UUID

from app.models.accounts import User
from app.models.collaboration.workspace import CommentMixin, CommentReaction, LinkPreview
from app.presenters.base import BasePresenter
from config.enums import LinkPreviewStatus
from lib.markdown import markdown_to_plain_text

CommentMixinType = TypeVar("CommentMixinType", bound=CommentMixin)
CommentPresenterType = TypeVar("CommentPresenterType", bound="CommentPresenter")


class CommentPresenter[CommentMixinType: CommentMixin](BasePresenter[CommentMixinType]):
    reaction_users: list[User]
    link_preview: LinkPreview | None = None

    def __init__(self, model: CommentMixinType, reaction_users: list[User]):
        super().__init__(model=model)
        self.reaction_users = reaction_users

    @property
    def has_ready_link_preview(self) -> bool:
        return self.link_preview is not None and self.link_preview.status == LinkPreviewStatus.READY

    @property
    def content_without_preview_url(self) -> str:
        content = self.model.content
        if self.has_ready_link_preview and self.link_preview:
            url = self.link_preview.url
            escaped_url = re.escape(url)
            content = re.sub(rf"\[{escaped_url}\]\({escaped_url}\)", "", content)
            content = re.sub(r"(?<!\()" + escaped_url + r"(?!\))", "", content)
            content = content.strip()
        return content

    @property
    def preview_text(self) -> str:
        return markdown_to_plain_text(self.content_without_preview_url)

    @classmethod
    async def create_from_list(
        cls: type[CommentPresenterType], comments: list[CommentMixinType]
    ) -> list[CommentPresenterType]:
        all_user_ids = {
            user_id for comment in comments for user_ids in comment.reactions.values() for user_id in user_ids
        }
        all_users = await User.filter(id__in=all_user_ids).all()
        users_by_id = {user.id: user for user in all_users}
        presenters = cls.create_from_list_with_users(comments, users_by_id)

        link_preview_ids = {p.model.link_preview_id for p in presenters if p.model.link_preview_id}
        if link_preview_ids:
            link_previews = await LinkPreview.filter(id__in=link_preview_ids)
            link_preview_by_id = {lp.id: lp for lp in link_previews}
            for presenter in presenters:
                if presenter.model.link_preview_id:
                    presenter.link_preview = link_preview_by_id.get(presenter.model.link_preview_id)

        return presenters

    @classmethod
    def create_from_list_with_users(
        cls: type[CommentPresenterType],
        comments: list[CommentMixinType],
        users_by_id: dict[UUID, User],
    ) -> list[CommentPresenterType]:
        result: list[CommentPresenterType] = []
        for comment in comments:
            comment_user_ids = {user_id for user_ids in comment.reactions.values() for user_id in user_ids}
            reaction_users = [users_by_id[user_id] for user_id in comment_user_ids if user_id in users_by_id]
            result.append(cls(model=comment, reaction_users=reaction_users))
        return result

    @property
    def reactions_with_users(self):
        return {
            CommentReaction.by_type(reaction_type): [user for user in self.reaction_users if user.id in user_ids]
            for reaction_type, user_ids in self.model.reactions.items()
        }
