import asyncio
from dataclasses import dataclass
from datetime import datetime

from app.helpers.users import user_avatar_url
from app.models.accounts import User
from app.models.collaboration.content import ContentLookup
from app.models.workspaces.email.contact import EmailContact
from app.presenters.base import BasePresenter
from config.enums import ContentType
from infra.db import RecordModel


class LookupResultPresenter(BasePresenter[ContentLookup]):
    source_model: RecordModel | None

    def __init__(self, model: ContentLookup, source_model: RecordModel | None = None):
        super().__init__(model=model)
        self.source_model = source_model

    def shared_with_me(self, current_user: User) -> bool:
        if self.model.content_type != ContentType.EMAIL_THREAD:
            return False
        # owner_user_id is round-tripped as a UUID via JSONField's custom encoder.
        owner_user_id = self.model.metadata.get("owner_user_id")
        return bool(owner_user_id and owner_user_id != current_user.id)

    @property
    def display_at(self) -> datetime:
        if self.model.content_type == ContentType.MEETING:
            scheduled_at = self.model.metadata.get("scheduled_at")
            if scheduled_at:
                return datetime.fromisoformat(scheduled_at) if isinstance(scheduled_at, str) else scheduled_at
        return self.model.updated_at

    @property
    def preview(self) -> str | None:
        if self.model.content_type == ContentType.CHAT:
            return self.model.preview_content_normalized
        return None

    @property
    def email(self) -> str | None:
        return getattr(self.source_model, "email", None)

    @property
    def avatar_url(self) -> str | None:
        if isinstance(self.source_model, User):
            return user_avatar_url(self.source_model)
        return None


@dataclass
class LookupResultsPresenter:
    user_results: list[LookupResultPresenter]
    other_results: list[LookupResultPresenter]

    @classmethod
    async def create(cls, results: list[ContentLookup], current_user: User) -> "LookupResultsPresenter":
        user_results = [r for r in results if r.content_type == ContentType.USER]
        email_contact_results = [r for r in results if r.content_type == ContentType.EMAIL_CONTACT]

        user_ids = [r.source_global_id.record_id for r in user_results]
        contact_ids = [r.source_global_id.record_id for r in email_contact_results]

        # Runs on every keystroke — fetch the two id-keyed lookups concurrently.
        users, contacts = await asyncio.gather(
            User.filter(id__in=user_ids).select_related("avatar_file").all(),
            EmailContact.filter(id__in=contact_ids).all(),
        )

        source_objects_by_id: dict[str, RecordModel] = {}
        source_objects_by_id.update({str(u.id): u for u in users})
        source_objects_by_id.update({str(c.id): c for c in contacts})

        # Pin the top-scoring chat to the front of other_results so chats aren't buried
        # by recency-weighted emails/docs. SQL returns content score-ordered within its
        # branch, so the first CHAT we see is the winner.
        chat_presenter: LookupResultPresenter | None = None
        user_presenters = []
        other_presenters = []

        for result in results:
            source_model = None
            if result.content_type in (ContentType.USER, ContentType.EMAIL_CONTACT):
                source_model = source_objects_by_id.get(str(result.source_global_id.record_id))

            presenter = LookupResultPresenter(model=result, source_model=source_model)

            if result.content_type in (ContentType.USER, ContentType.EMAIL_CONTACT):
                user_presenters.append(presenter)
            elif result.content_type == ContentType.CHAT and chat_presenter is None:
                chat_presenter = presenter
            else:
                other_presenters.append(presenter)

        if chat_presenter is not None:
            other_presenters.insert(0, chat_presenter)

        return cls(user_results=user_presenters, other_results=other_presenters)

    @property
    def has_separator(self) -> bool:
        return len(self.user_results) > 0 and len(self.other_results) > 0

    @property
    def content_ids(self) -> list[str]:
        return [str(presenter.model.id) for presenter in self.user_results + self.other_results]

    def __len__(self) -> int:
        return len(self.user_results) + len(self.other_results)
