from datetime import datetime
from functools import cached_property

from app.models.accounts import User
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Decision, WorkspaceMixin
from app.models.workspaces.chat import Chat
from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.thread import EmailThread
from app.models.workspaces.goals import GoalUpdate
from app.models.workspaces.posts import Post
from app.presenters.base import BasePresenter
from infra.db import GlobalID, RecordModel

RESOURCE_PREFETCH: dict[str, list[str]] = {
    "EmailThread": ["messages__attachments", "workspace__attachments", "workspace__collaborators__user__avatar_file"],
    "Post": ["workspace__collaborators__user__avatar_file", "creator__avatar_file", "group"],
    "Goal": ["workspace__collaborators__user__avatar_file", "creator__avatar_file", "owner__avatar_file"],
    "Chat": ["workspace__collaborators__user__avatar_file", "last_message__user__avatar_file", "group"],
}

# body_preview reads a post's first comment, but that's only rendered in the AI
# view/sort prompts — loading every visible post's comments on the hot list
# endpoints would be wasted work, so it's an opt-in prefetch (include_body).
PROMPT_RESOURCE_PREFETCH: dict[str, list[str]] = {
    **RESOURCE_PREFETCH,
    "Post": [*RESOURCE_PREFETCH["Post"], "comments"],
}


class MailboxEntryPresenter(BasePresenter[MailboxEntry]):
    current_user_email: str | None = None
    resource: RecordModel | None = None
    # True when a Post resource's workspace has any decision (the inbox indicator),
    # derived from the Decision model in _load_resources.
    post_is_decided: bool = False

    @classmethod
    def create(cls, mailbox_entry: MailboxEntry, current_user_email: str | None = None):
        return cls(mailbox_entry, current_user_email=current_user_email)

    @classmethod
    async def create_from_list(
        cls,
        mailbox_entries: list[MailboxEntry],
        current_user_email: str | None = None,
        include_body: bool = False,
    ) -> list["MailboxEntryPresenter"]:
        presenters = [cls.create(mailbox_entry, current_user_email) for mailbox_entry in mailbox_entries]
        await cls._load_resources(presenters, include_body=include_body)
        return presenters

    @classmethod
    async def _load_resources(cls, presenters: list["MailboxEntryPresenter"], include_body: bool = False) -> None:
        gids = [p.model.resource_gid for p in presenters if p.model.resource_gid]
        if not gids:
            return

        prefetch_map = PROMPT_RESOURCE_PREFETCH if include_body else RESOURCE_PREFETCH
        records = await GlobalID.bulk_fetch(gids, prefetch_map=prefetch_map)

        owner_ids = {p.model.owner_id for p in presenters if p.model.resource_gid and p.model.owner_id}
        owners_by_id = {u.id: u for u in await User.filter(id__in=owner_ids)} if owner_ids else {}

        for presenter in presenters:
            gid = presenter.model.resource_gid
            if gid:
                resource = records.get((gid.record_type, gid.record_id))
                if resource and gid.record_type in prefetch_map:
                    owner = owners_by_id.get(presenter.model.owner_id)
                    if owner and cls._can_access_resource(resource, owner):
                        presenter.resource = resource

        await cls._load_post_decisions(presenters)

    @classmethod
    async def _load_post_decisions(cls, presenters: list["MailboxEntryPresenter"]) -> None:
        # The inbox post indicator is "has any decision" — derive it from the
        # Decision model (the legacy Post.decided_at column is gone) with one query.
        workspace_ids = [p.resource.workspace_id for p in presenters if isinstance(p.resource, Post)]
        if not workspace_ids:
            return
        # order_by clears the model's default decided_at ordering, which SELECT
        # DISTINCT rejects; dedup in Postgres rather than loading every row.
        decided = (
            Decision.filter(workspace_id__in=workspace_ids)
            .order_by("workspace_id")
            .distinct()
            .values_list("workspace_id", flat=True)
        )
        decided_workspace_ids = set(await decided)
        for presenter in presenters:
            if isinstance(presenter.resource, Post):
                presenter.post_is_decided = presenter.resource.workspace_id in decided_workspace_ids

    @staticmethod
    def _can_access_resource(record: RecordModel, user: User) -> bool:
        if isinstance(record, WorkspaceMixin):
            return record.collaboration.can_be_accessed_by(user)
        if isinstance(record, GoalUpdate):
            return record.goal.collaboration.can_be_accessed_by(user)
        return False

    @property
    def email_thread(self) -> EmailThread | None:
        if isinstance(self.resource, EmailThread):
            return self.resource
        return None

    @property
    def post(self) -> Post | None:
        if isinstance(self.resource, Post):
            return self.resource
        return None

    @property
    def chat(self) -> Chat | None:
        if isinstance(self.resource, Chat):
            return self.resource
        return None

    @property
    def email_message_count(self) -> int:
        if self.email_thread:
            return len(self.email_thread.messages)
        return 0

    @property
    def email_attachment_count(self) -> int:
        if self.email_thread:
            return sum(len(msg.attachments) for msg in self.email_thread.messages if msg.attachments)
        return 0

    @property
    def scheduled_send_at(self) -> datetime | None:
        """When this thread's draft is scheduled to send, if any (reads prefetched messages)."""
        return self.email_thread.scheduled_send_at if self.email_thread else None

    @property
    def sender_names(self) -> list[str]:
        return [addr.display_name for addr in self._sender_addresses_unique]

    @cached_property
    def _sender_addresses_chronological(self) -> list[EmailAddress]:
        if self.email_thread:
            return self.email_thread.sender_addresses_chronological
        return []

    @cached_property
    def _sender_addresses_unique(self) -> list[EmailAddress]:
        if self.email_thread:
            return self.email_thread.sender_addresses_unique
        return []

    @property
    def original_sender(self) -> EmailAddress | None:
        addresses = self._sender_addresses_chronological
        return addresses[0] if addresses else None

    @property
    def count_senders(self) -> int:
        return len(self._sender_addresses_unique)

    @property
    def most_recent_sender(self) -> EmailAddress | None:
        sender_addresses = self._sender_addresses_chronological
        if len(sender_addresses) <= 1:
            return None

        most_recent = None
        for sender in reversed(sender_addresses[1:]):
            if not self.current_user_email or sender.email != self.current_user_email:
                most_recent = sender
                break

        if (
            most_recent
            and self.original_sender
            and most_recent.email == self.original_sender.email
            and self.count_senders == 1
        ):
            return None

        return most_recent

    @property
    def is_group_chat(self) -> bool:
        return isinstance(self.resource, Chat) and self.resource.group_id is not None

    @property
    def is_direct_message(self) -> bool:
        return (
            isinstance(self.resource, Chat)
            and self.resource.group_id is None
            and len(self.resource.workspace.collaborators) == 2
        )

    @property
    def chat_counterparty(self) -> User | None:
        if not isinstance(self.resource, Chat) or not self.is_direct_message:
            return None
        other = next((c for c in self.resource.workspace.collaborators if c.user_id != self.model.owner_id), None)
        if other and other.user:
            return other.user
        return None

    @property
    def additional_sender_count(self) -> int:
        if (
            self.original_sender
            and self.most_recent_sender
            and self.original_sender.display_name == self.most_recent_sender.display_name
        ):
            return max(self.count_senders - 1, 0)
        return max(self.count_senders - 2, 0)

    # Prompt-facing fields for mailbox-view generation. Emails, posts, and chats each carry
    # meaning in different places, so the email-shaped `sender_names`/`email_message_count`
    # render blank for posts/chats and the model under-files them. These expose type-appropriate
    # context so every resource type reads as a substantive item.

    @property
    def item_type(self) -> str:
        match self.model.resource_type:
            case "EmailThread":
                return "Email"
            case "Post":
                return "Post"
            case "Chat":
                return "Chat"
            case "Goal":
                return "Goal"
            case _:
                return "Item"

    @property
    def author_name(self) -> str | None:
        """Who the item is from: email senders, the post author, or the chat's latest speaker."""
        if self.email_thread:
            return ", ".join(self.sender_names) or None
        if self.post and self.post.creator:
            return self.post.creator.display_name
        if self.chat:
            if self.chat.last_message and self.chat.last_message.user:
                return self.chat.last_message.user.display_name
            counterparty = self.chat_counterparty
            return counterparty.display_name if counterparty else None
        return None

    @property
    def audience(self) -> str | None:
        """Who the item is shared with: a post's group/org, or a chat's group or participants."""
        if self.post:
            return self.post.group.name if self.post.group else "Whole organization"
        if self.chat:
            # Branch on the chat shape up front so a group chat whose group is missing (deleted, or
            # not prefetched) falls back to a group label rather than dropping through and leaking
            # the full collaborator list under a "Chat with …" heading.
            if self.is_group_chat:
                return self.chat.group.name if self.chat.group else "Group chat"
            if self.is_direct_message:
                counterparty = self.chat_counterparty
                return f"Direct message with {counterparty.display_name}" if counterparty else "Direct message"
            names = [c.user.display_name for c in self.chat.workspace.collaborators if c.user]
            return f"Chat with {', '.join(names)}" if names else None
        return None

    @property
    def body_preview(self) -> str:
        """The item's body content for prompt context."""
        # Each resource type stores its body in a different place, and the entry's denormalized
        # columns only cover some of them: emails populate `preview` (the thread snippet) and chats
        # populate `last_comment` (the last message), but posts leave both empty — their body lives
        # in the post's own first comment. Surface whichever carries real content so the model never
        # scores a post or chat on its bare title.
        if self.post:
            comment = self.post.original_comment
            if comment and comment.content:
                return comment.content
        return self.model.preview or self.model.last_comment or ""
