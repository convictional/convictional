from dataclasses import dataclass
from datetime import datetime

from app.models.collaboration.content import Content
from infra.db import TSVectorField


class SlackContent(Content):
    lookup_search = TSVectorField(null=True, description="protected_column")


@dataclass
class SlackMessage:
    message_id: str
    channel_id: str
    channel_name: str
    text: str
    timestamp: str
    username: str
    permalink: str
    team_id: str
    thread_ts: str | None = None

    @property
    def datetime(self) -> str:
        ts_float = float(self.timestamp)
        dt = datetime.fromtimestamp(ts_float)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class ExpandedMessageContext:
    matched_message: SlackMessage
    is_thread_reply: bool = False
    # For top-level messages: surrounding channel context
    prior_messages: list[SlackMessage] | None = None
    subsequent_messages: list[SlackMessage] | None = None
    thread_replies: list[SlackMessage] | None = None
    # For thread replies: the full thread including parent
    full_thread: list[SlackMessage] | None = None

    def to_text(self) -> str:
        lines: list[str] = []
        matched = self.matched_message

        lines.append(f"Channel: #{matched.channel_name}")
        lines.append("")

        if self.is_thread_reply and self.full_thread:
            lines.append("This is a thread conversation. The search matched a reply within this thread.")
            lines.append("")
            for msg in self.full_thread:
                prefix = "[MATCHED] " if msg.timestamp == matched.timestamp else ""
                lines.append(f"{prefix}{msg.username}: {msg.text}")
        else:
            if self.prior_messages or self.subsequent_messages:
                lines.append("Messages in channel around the matched message:")
                lines.append("")
                for msg in self.prior_messages or []:
                    lines.append(f"{msg.username}: {msg.text}")

                lines.append(f"[MATCHED] {matched.username}: {matched.text}")

                for msg in self.subsequent_messages or []:
                    lines.append(f"{msg.username}: {msg.text}")
            else:
                lines.append(f"[MATCHED] {matched.username}: {matched.text}")

            if self.thread_replies:
                lines.append("")
                lines.append("Thread replies to the matched message:")
                for reply in self.thread_replies:
                    lines.append(f"  {reply.username}: {reply.text}")

        return "\n".join(lines)
