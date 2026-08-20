import re

from app.models.collaboration.workspace import WorkspaceMixin
from app.models.workspaces.goals import Goal

_WHITESPACE_RUN = re.compile(r"\s+")


def resource_label(resource: WorkspaceMixin) -> str:
    # Most resources have a non-null `title`, but Goal makes it nullable and
    # stores the substantive text in `description`. Email Thread titles
    # mirror the original Subject header, which can be empty. Fall back to a
    # placeholder so subjects never render as just `""`.
    #
    # `description` in particular is a multi-line TextField; collapsing
    # internal whitespace keeps the value safe for use in an email Subject
    # header (RFC 5322 forbids bare newlines in header field bodies).
    # Length is intentionally not capped: production data shows long
    # descriptions are always paired with a non-empty `title`, so the
    # fallback branch only fires when description is already short.
    candidate = (resource.title or "").strip()
    if not candidate and isinstance(resource, Goal):
        candidate = resource.description.strip()
    return _WHITESPACE_RUN.sub(" ", candidate) or "(untitled)"


ICON_MAP = {
    "emailthread": "mail",
    "emailcontact": "contact_mail",
    "meeting": "calendar_month",
    "meetingtranscript": "transcribe",
    "goal": "target",
    "post": "forum",
    "postcomment": "comment",
    "comment": "comment",
    "file": "description",
    "user": "person",
    "update": "notifications",
    "chat": "chat",
    "group": "groups",
}


def resource_icon(resource_type: str) -> str:
    """Return the icon name for a given resource type string, like 'emailthread', 'EmailThread', or 'email_thread'."""
    normalized = "".join(c.lower() for c in resource_type if c.isalnum())
    return ICON_MAP.get(normalized, "description")
