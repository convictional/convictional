import contextlib
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import frontmatter
import yaml
from frontmatter.default_handlers import YAMLHandler
from tortoise import Tortoise

import config.enums as enums_module
from app.models.collaboration.mailbox import Mailbox
from app.models.workspaces.chat import Chat, ChatMessage
from app.models.workspaces.posts import Post
from infra.db import GlobalID, RecordModel
from scripts.seeds.seeder import Ref, _current, create, prefix, seed_id

_WEEKDAY_NAMES = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


@dataclass(frozen=True)
class Attendee:
    user: Ref
    is_organizer: bool = False


def _time_at(tz: ZoneInfo, offset_days: int, hour: int, minute: int) -> datetime:
    now = datetime.now(tz)
    target = (now + timedelta(days=offset_days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target.astimezone(UTC)


def _next_weekday_constructor(loader, node):
    data = loader.construct_mapping(node)
    tz = ZoneInfo(data.get("tz", "America/New_York"))
    weekday = _WEEKDAY_NAMES[data["day"]]
    days_ahead = (weekday - datetime.now(tz).weekday()) % 7 or 7
    return _time_at(tz, days_ahead, data.get("hour", 0), data.get("minute", 0))


def _relative_day_constructor(loader, node):
    data = loader.construct_mapping(node)
    tz = ZoneInfo(data.get("tz", "America/New_York"))
    return _time_at(tz, data["offset"], data.get("hour", 0), data.get("minute", 0))


@dataclass(frozen=True)
class ResourceRef:
    model: str
    ref: Ref

    @property
    def gid(self) -> GlobalID:
        return GlobalID.create(self.model, self.ref.id)


def _attendee_constructor(loader, node):
    data = loader.construct_mapping(node)
    return Attendee(user=Ref(data["user"]), is_organizer=data.get("is_organizer", False))


def _resource_ref_constructor(loader, node):
    data = loader.construct_mapping(node)
    return ResourceRef(model=data["model"], ref=Ref(data["ref"]))


class _SeedLoader(yaml.SafeLoader):
    pass


_SeedLoader.add_constructor("!ref", lambda loader, node: Ref(loader.construct_scalar(node)))
_SeedLoader.add_constructor(
    "!days_from_now",
    lambda loader, node: date.today() + timedelta(days=int(loader.construct_scalar(node))),
)
_SeedLoader.add_constructor("!next_weekday", _next_weekday_constructor)
_SeedLoader.add_constructor("!relative_day", _relative_day_constructor)
_SeedLoader.add_constructor("!attendee", _attendee_constructor)
_SeedLoader.add_constructor("!resource_ref", _resource_ref_constructor)


class _SeedYAMLHandler(YAMLHandler):
    def load(self, fm, **kwargs):
        return yaml.load(fm, Loader=_SeedLoader)


_seed_handler = _SeedYAMLHandler()


def _build_enum_lookup() -> dict[str, Enum]:
    lookup: dict[str, Enum] = {}
    for obj in vars(enums_module).values():
        if isinstance(obj, type) and issubclass(obj, Enum) and obj is not Enum:
            for member in obj:
                if isinstance(member.value, str):
                    lookup[member.value] = member
    return lookup


_ENUM_LOOKUP = _build_enum_lookup()


@dataclass
class FrontMatter:
    key: str | None
    model: str | None
    body: str
    fields: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "FrontMatter":
        post = frontmatter.load(str(path), handler=_seed_handler)
        meta: dict[str, Any] = dict(post.metadata)
        return cls(
            key=meta.pop("key", None),
            model=meta.pop("model", None),
            body=post.content.strip(),
            fields=meta,
        )


@dataclass
class ContentSeeder:
    content_dir: Path

    _SEED_URL_RE = re.compile(r'seed:(\w+)/([^"]+)')

    def _resolve_body_refs(self, body: str) -> str:
        namespace = _current.get().namespace

        def _replace(match: re.Match[str]) -> str:
            route = match.group(1)
            key = match.group(2)
            uid = seed_id(f"{namespace}-{key}")
            return f"/{route}/{uid}"

        return self._SEED_URL_RE.sub(_replace, body)

    def _resolve(self, meta: dict[str, Any], local: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved = {}
        for k, v in meta.items():
            if not isinstance(v, str):
                resolved[k] = v
                continue
            if local and v in local:
                resolved[k] = local[v]
            elif v in _ENUM_LOOKUP:
                resolved[k] = _ENUM_LOOKUP[v]
            else:
                resolved[k] = v
        return resolved

    async def seed_dir(
        self,
        subdir: str,
        **defaults: Any,
    ):
        model_lookup = cast(dict[str, type[RecordModel]], Tortoise.apps["convictional"])
        dir_path = self.content_dir / subdir

        for dirpath_str, dirnames, filenames in os.walk(dir_path):
            current = Path(dirpath_str)
            rel_parts = current.relative_to(dir_path).parts
            dir_prefix = "-".join(rel_parts)
            local: dict[str, RecordModel] = {}

            dirnames[:] = [d for d in sorted(dirnames) if d != "recurring"]
            ctx = prefix(dir_prefix) if dir_prefix else contextlib.nullcontext()
            with ctx:
                for filename in sorted(filenames):
                    if not filename.endswith(".md"):
                        continue

                    fm = FrontMatter.load(current / filename)
                    assert fm.key, f"Missing 'key' in frontmatter: {filename}"
                    assert fm.model, f"Missing 'model' in frontmatter: {filename}"
                    model = model_lookup[fm.model]
                    resolved = self._resolve(fm.fields, local=local if rel_parts else None)

                    kwargs = {**defaults, **resolved}
                    if fm.body:
                        kwargs["content"] = self._resolve_body_refs(fm.body)

                    instance = await create(model, fm.key, **kwargs)
                    local[fm.key] = instance

    async def seed_recurring_meetings(self, subdir: str = "meetings/recurring", days_ahead: int = 14, **defaults: Any):
        model_lookup = cast(dict[str, type[RecordModel]], Tortoise.apps["convictional"])
        dir_path = self.content_dir / subdir
        if not dir_path.exists():
            return

        today = date.today()

        for filename in sorted(os.listdir(dir_path)):
            if not filename.endswith(".md"):
                continue

            fm = FrontMatter.load(dir_path / filename)
            stem = Path(filename).stem

            weekdays = fm.fields.pop("weekdays", [])
            hour = fm.fields.pop("hour", 0)
            minute = fm.fields.pop("minute", 0)
            tz_name = fm.fields.pop("tz", "America/New_York")
            tz = ZoneInfo(tz_name)

            assert fm.model, f"Missing 'model' in frontmatter: {filename}"
            model = model_lookup[fm.model]
            resolved = self._resolve(fm.fields)

            for offset in range(1, days_ahead + 1):
                target_date = today + timedelta(days=offset)
                if target_date.weekday() not in weekdays:
                    continue

                scheduled_at = datetime(
                    target_date.year,
                    target_date.month,
                    target_date.day,
                    hour,
                    minute,
                    tzinfo=tz,
                ).astimezone(UTC)

                kwargs = {**defaults, **resolved, "scheduled_at": scheduled_at}
                if fm.body:
                    kwargs["content"] = fm.body

                await create(model, f"{stem}-day-{offset}", **kwargs)

    async def seed_chats(self, subdir: str = "chats", **defaults: Any) -> None:
        dir_path = self.content_dir / subdir
        if not dir_path.exists():
            return

        for filename in sorted(os.listdir(dir_path)):
            if not filename.endswith(".yaml"):
                continue

            with open(dir_path / filename) as f:
                data = yaml.load(f, Loader=_SeedLoader)

            chat_key = data["key"]
            member_keys = data.get("members", [])
            member_ids = [Ref(m).id for m in member_keys]
            # First-listed member is the seed creator. WorkspaceMixin requires it; the
            # post_save(Workspace) signal uses creator_id to seed the first Collaborator.
            creator_id = member_ids[0] if member_ids else None

            chat_kwargs: dict[str, Any] = {**defaults, "creator_id": creator_id}
            if "name" in data:
                chat_kwargs["title"] = data["name"]
            if "group" in data:
                chat_kwargs["group"] = Ref(data["group"])
            else:
                # Non-group chats (DMs, multi) require collaborators_hash for uniqueness.
                chat_kwargs["collaborators_hash"] = Chat.compute_collaborators_hash(member_ids)

            chat = await create(Chat, chat_key, **chat_kwargs)

            # Mirror production chat creation: Collaborator rows on the workspace are the
            # source of truth for chat membership (post the workspace migration).
            if member_ids:
                await Chat.upsert_collaborators(chat.workspace_id, member_ids, creator_id)

            # Two-pass: materialize messages, then update Chat.last_message
            message_lookup: dict[str, ChatMessage] = {}
            last_message: ChatMessage | None = None
            for msg in data.get("messages", []):
                msg_key = msg["key"]
                msg_kwargs: dict[str, Any] = {
                    "chat": chat,
                    "user": Ref(msg["author"]),
                }
                if "content" in msg:
                    msg_kwargs["content"] = msg["content"]
                if "at" in msg:
                    msg_kwargs["created_at"] = msg["at"]
                if "reactions" in msg:
                    msg_kwargs["reactions"] = msg["reactions"]
                if "reply_to" in msg:
                    reply_key = msg["reply_to"]
                    if reply_key in message_lookup:
                        msg_kwargs["reply_to"] = message_lookup[reply_key]
                message = await create(ChatMessage, msg_key, **msg_kwargs)
                message_lookup[msg_key] = message
                last_message = message

            if last_message is not None:
                chat.last_message_id = last_message.id
                chat.last_message_at = last_message.created_at
                await chat.save(update_fields=["last_message_id", "last_message_at"])

    async def sync_post_mailbox_entries(self, organization: RecordModel) -> None:
        # Create native PostMailboxEntry records (not fake emails) for every subscriber
        # of every seeded post. In production, Mailbox.sync(post) runs automatically when
        # a comment is added to a post; seeds don't hit that path so we invoke
        # it explicitly here, after posts + subscriptions exist.
        posts = await Post.filter(organization_id=organization.id).prefetch_related("creator")
        for post in posts:
            await Mailbox.sync(post)

    async def sync_chat_mailbox_entries(self, organization: RecordModel) -> None:
        # Create native ChatMailboxEntry records for every member of every seeded chat,
        # so new chats show up in each participant's inbox. Mirrors sync_post_mailbox_entries.
        chats = await Chat.filter(organization_id=organization.id)
        for chat in chats:
            await Mailbox.sync(chat)
