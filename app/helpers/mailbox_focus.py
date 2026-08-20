from dataclasses import dataclass
from uuid import UUID

from app.models.accounts import User
from app.models.collaboration.mailbox import MAILBOX_VIEW_TEMPLATES, MailboxView
from app.models.workspaces.goals import Goal
from config.enums import Integration, MailboxSort
from lib.uuid import parse_uuid

# The onboarding focus is client-rendered (MailboxIndex draws its cards), so it is
# deliberately NOT a MAILBOX_VIEW_TEMPLATES entry — the server never generates a view
# for it. It only rides the focus-preference cookie so selection/exit behave like any
# other focus.
# Mirror: GETTING_STARTED_TEMPLATE in MailboxIndex.tsx — change both together.
GETTING_STARTED_TEMPLATE = "getting_started"


@dataclass(frozen=True)
class MailboxFocus:
    # A focus is one selection, so at most one of these is set; the default focus sets none.
    # `sort=NEWEST` is the default and is stored as an explicit "no focus" choice, so it
    # normalizes away here — nothing is set and the inbox URL carries no params.
    sort: MailboxSort | None = None
    mailbox_view_template: str | None = None
    goal_id: UUID | None = None
    mailbox_view_id: UUID | None = None

    @property
    def query_params(self) -> dict[str, str]:
        """The focus as inbox URL query params — empty for the default focus."""
        if self.sort is not None:
            return {"sort": self.sort.value}
        if self.mailbox_view_template is not None:
            params = {"mailbox_view_template": self.mailbox_view_template}
            if self.goal_id is not None:
                params["goal_id"] = str(self.goal_id)
            return params
        if self.mailbox_view_id is not None:
            return {"mailbox_view_id": str(self.mailbox_view_id)}
        return {}

    @property
    def cookie_value(self) -> str:
        """The stored form of the focus — empty for the default focus, which is never stored."""
        if self.sort is not None:
            return f"sort={self.sort.value}"
        # The "by_goal" focus carries a target goal, so the stored value must keep BOTH the
        # template and the goal_id together — a single key=value pair can't, hence the &-joined form.
        if self.mailbox_view_template is not None:
            if self.goal_id is not None:
                return f"mailbox_view_template={self.mailbox_view_template}&goal_id={self.goal_id}"
            return f"mailbox_view_template={self.mailbox_view_template}"
        if self.mailbox_view_id is not None:
            return f"mailbox_view_id={self.mailbox_view_id}"
        return ""


@dataclass(frozen=True)
class ResolvedMailboxFocus:
    focus: MailboxFocus
    # The stored preference was malformed, named an unknown template, or pointed at a goal or
    # saved view the user can no longer reach. Callers drop to the default focus and clear it.
    stale: bool = False
    # Whether `focus` is what the stored preference already says. False when it came from the
    # onboarding default, which callers persist so that clearing the focus opts out permanently.
    stored: bool = False


def is_valid_focus_template(template: str) -> bool:
    return template == GETTING_STARTED_TEMPLATE or template in MAILBOX_VIEW_TEMPLATES


async def resolve_mailbox_focus(stored_value: str | None, current_user: User) -> ResolvedMailboxFocus:
    """Turn the stored focus preference into a focus the inbox can actually render."""
    if not stored_value:
        # New users have no saved focus preference yet; default them into the onboarding
        # "Getting started" focus while setup is unfinished.
        if _onboarding_incomplete(current_user):
            return ResolvedMailboxFocus(MailboxFocus(mailbox_view_template=GETTING_STARTED_TEMPLATE))
        return ResolvedMailboxFocus(MailboxFocus())

    key, separator, value = stored_value.partition("=")
    if not separator or not value:
        return _stale()

    if key == "sort":
        try:
            sort = MailboxSort(value)
        except ValueError:
            return _stale()
        # NEWEST is the default, so it resolves to the default focus and leaves the URL bare.
        return _stored(MailboxFocus(sort=sort if sort != MailboxSort.NEWEST else None))

    if key == "mailbox_view_template":
        # Value is "<template>" or, for by_goal, "<template>&goal_id=<uuid>".
        template, _, raw_goal_id = value.partition("&goal_id=")
        if not is_valid_focus_template(template):
            return _stale()
        if not raw_goal_id:
            return _stored(MailboxFocus(mailbox_view_template=template))
        goal_id = parse_uuid(raw_goal_id)
        if goal_id is None:
            return _stale()
        # Stale goal (deleted, or now foreign) → drop to the plain inbox rather than a focus
        # that can't generate.
        if not await Goal.filter(id=goal_id, organization_id=current_user.organization_id).exists():
            return _stale()
        return _stored(MailboxFocus(mailbox_view_template=template, goal_id=goal_id))

    if key == "mailbox_view_id":
        view_id = parse_uuid(value)
        if view_id is None:
            return _stale()
        exists = await MailboxView.filter(
            MailboxView.filters.by_user(current_user.id),
            MailboxView.filters.by_organization(current_user.organization_id),
            id=view_id,
        ).exists()
        if not exists:
            return _stale()
        return _stored(MailboxFocus(mailbox_view_id=view_id))

    return _stale()


def _onboarding_incomplete(user: User) -> bool:
    # Onboarding is complete once Gmail and Calendar are both connected. It's a Google-integration
    # flow, so Microsoft users (who can connect neither) are never "incomplete" — otherwise they'd
    # be auto-redirected into the focus on every cookieless visit with no way to satisfy it.
    if user.authentication.is_microsoft:
        return False
    return not (user.is_integrated_with(Integration.GMAIL) and user.is_integrated_with(Integration.RECALL_AI_CALENDAR))


def _stale() -> ResolvedMailboxFocus:
    return ResolvedMailboxFocus(MailboxFocus(), stale=True)


def _stored(focus: MailboxFocus) -> ResolvedMailboxFocus:
    return ResolvedMailboxFocus(focus, stored=True)
