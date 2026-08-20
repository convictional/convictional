from typing import ClassVar

from tortoise import BaseDBAsyncClient, signals
from tortoise.expressions import Q

from config.enums import EmailLabel
from infra.db import JSONField, RecordModel


class EmailLabelFilters:
    inbox: ClassVar[Q] = (
        Q(labels__contains=[EmailLabel.INBOX]) & ~Q(labels__contains=[EmailLabel.SPAM]) & ~Q(labels=[EmailLabel.SENT])
    )
    sent: ClassVar[Q] = Q(labels__contains=[EmailLabel.SENT])
    draft: ClassVar[Q] = Q(labels__contains=[EmailLabel.DRAFT])
    archived: ClassVar[Q] = (
        ~Q(labels__contains=[EmailLabel.INBOX])
        & ~Q(labels__contains=[EmailLabel.DRAFT])
        & ~Q(labels__contains=[EmailLabel.SPAM])
    )


class EmailLabelsMixin(RecordModel):
    labels = JSONField[list[EmailLabel]](default=list)

    class Meta:
        abstract = True

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        signals.pre_save(cls)(sort_email_labels)

    @classmethod
    def normalize_labels(cls, labels: list) -> list:
        return sorted(set(labels))

    @property
    def is_inbox(self) -> bool:
        return EmailLabel.INBOX in self.labels

    @property
    def is_sent(self) -> bool:
        return EmailLabel.SENT in self.labels

    @property
    def is_spam(self) -> bool:
        return EmailLabel.SPAM in self.labels

    @property
    def is_archived(self) -> bool:
        return (
            EmailLabel.INBOX not in self.labels
            and EmailLabel.SPAM not in self.labels
            and EmailLabel.DRAFT not in self.labels
        )

    @property
    def is_draft(self) -> bool:
        return EmailLabel.DRAFT in self.labels

    @property
    def has_draft(self) -> bool:
        return self.is_draft

    @property
    def is_unread(self) -> bool:
        return EmailLabel.UNREAD in self.labels

    @property
    def is_read(self) -> bool:
        return EmailLabel.UNREAD not in self.labels

    def label_as_inbox(self) -> None:
        if not self.is_inbox:
            self.labels.append(EmailLabel.INBOX)

    def label_as_read(self) -> None:
        if self.is_unread:
            self.labels.remove(EmailLabel.UNREAD)

    def label_as_unread(self) -> None:
        if not self.is_unread:
            self.labels.append(EmailLabel.UNREAD)

    def label_as_archived(self) -> None:
        if self.is_inbox:
            self.labels.remove(EmailLabel.INBOX)
        if self.is_spam:
            self.labels.remove(EmailLabel.SPAM)
        if self.is_draft:
            self.labels.remove(EmailLabel.DRAFT)

    def label_as_unarchived(self) -> None:
        if self.is_archived:
            self.labels.append(EmailLabel.INBOX)

    def label_as_sent(self) -> None:
        if not self.is_sent:
            self.labels.append(EmailLabel.SENT)

    def label_as_draft(self) -> None:
        if not self.is_draft:
            self.labels.append(EmailLabel.DRAFT)

    def label_as_not_draft(self) -> None:
        if self.is_draft:
            self.labels.remove(EmailLabel.DRAFT)

    def label_as_spam(self) -> None:
        if not self.is_spam:
            self.labels.append(EmailLabel.SPAM)


async def sort_email_labels(
    sender: "type[EmailLabelsMixin]",
    instance: EmailLabelsMixin,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    instance.labels = instance.normalize_labels(instance.labels)
