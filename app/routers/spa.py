from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.helpers.strings import page_title_prefix
from app.routers.dependencies import Helpers, backfill_user_timezone, get_helpers
from config import settings

# Paths served the client-routed SPA shell (see docs/react-migration.md →
# Client-Side Router ADR). Each path here gets the near-empty TanStack Router
# shell instead of a server-rendered Jinja page; everything else keeps its HTML
# router. A path is added here only when its page moves to client routing. The
# dev/test-only `/_spa` placeholder keeps the mechanism exercised even if every
# production path were ever removed.
#
# A path may carry a route `name` so `url_for(name)` resolves to the client route
# (there's no Jinja handler to own the name). Documents need this because
# `back_navigation` (app/helpers/url.py) and gid redirects target
# `documents_index`/`documents_show`/`documents_edit` by name — the
# `DocumentComment` gid redirect (global_ids.py) and the mention/comment mailers
# resolve `documents_edit` this way. Unnamed paths (notifications, organization
# edit) omit it.
SPA_ROUTES: list[tuple[str, str | None]] = [
    # All seven inbox paths need names: every one is a back-navigation fallback
    # (app/helpers/url.py — BackFallbackRoute / BACK_LABELS) and six are aliased onto
    # canonical view names in api/mailbox_entries.py. mailbox_index is resolved far more
    # widely still (auth.py, api/email_drafts.py, the 4xx page, the nav, the onboarding
    # mailer). _back_label_for_path swallows NoMatchFound, so a missing name
    # degrades silently into a wrong back-button label — hence the url_for assertions in
    # tests/integration/routers/test_spa.py.
    ("/", "mailbox_index"),
    ("/unread", "mailbox_unread"),
    ("/archived", "mailbox_archived"),
    ("/sent", "mailbox_sent"),
    ("/drafts", "mailbox_drafts"),
    ("/assigned_to_me", "mailbox_assigned_to_me"),
    ("/snoozed", "mailbox_snoozed"),
    ("/notifications", None),
    ("/organization/edit", None),
    ("/documents", "documents_index"),
    ("/documents/{document_id}", "documents_show"),
    ("/documents/{document_id}/edit", "documents_edit"),
    ("/posts", "posts_index"),
    ("/posts/{post_id}", "posts_show"),
    ("/posts/{post_id}/edit", "posts_edit"),
    # Goals need names too: the Goal / GoalComment gid redirects (global_ids.py)
    # and back_navigation's BACK_LABELS resolve goals_index, and the mailbox entry
    # href (api/mailbox_entries.py) resolves goals_show.
    ("/goals", "goals_index"),
    ("/goals/{goal_id}", "goals_show"),
    # Chat needs names too: back_navigation, the Chat gid redirect (global_ids.py),
    # and the mailbox entry href (api/mailbox_entries.py) resolve chats_index /
    # chats_show by name.
    ("/chats", "chats_index"),
    ("/chats/{chat_id}", "chats_show"),
    # Email threads need names too: the gid redirect (global_ids.py), the mailbox
    # entry href (api/mailbox_entries.py), and view_original_url
    # (api/email_threads.py) resolve email_threads_show / email_threads_show_original
    # by name.
    ("/email_threads/{email_thread_id}", "email_threads_show"),
    ("/email_threads/{email_thread_id}/email_messages/{email_message_id}", "email_threads_show_original"),
]
if settings.is_env("development", "test"):
    SPA_ROUTES.append(("/_spa", None))

SPA_PATHS: list[str] = [path for path, _ in SPA_ROUTES]

router = APIRouter(tags=["skip_onboarding"])


async def _render_shell(helpers: Helpers = Depends(get_helpers)) -> Response:
    # hx-boost is global on the legacy layout, so a link from any legacy (htmx)
    # page to a SPA route is fetched by htmx as a fragment rather than loaded as a
    # document. htmx-ext-head-support then merges this shell's <head> into the
    # legacy page and re-executes its inline bootstrap scripts in the wrong
    # document, which crashes ("Unexpected token '&'" while appending a shell <script>).
    # The shell is a standalone full document that boots its own bundle, so bounce any
    # htmx-initiated request to a real browser navigation; the follow-up
    # top-level GET (no HX-Request) serves the shell normally. A plain 3xx
    # won't do — htmx follows redirects as AJAX and still swaps;
    # HX-Redirect is what forces window.location.
    if helpers.connection.headers.get("hx-request") == "true":
        url = helpers.connection.url
        target = f"{url.path}?{url.query}" if url.query else url.path
        return helpers.no_content(redirect=target)

    # These paths were server-rendered pages behind get_current_user before the SPA
    # cutover, so the timezone backfill (a side effect of that dependency) rode every
    # authenticated load. The shell deliberately carries no get_current_user — the
    # client-side beforeLoad guards are the sole auth gate — so run the backfill here
    # instead, only when a user is actually present, keeping the "shell is served to
    # unauthenticated users without a server redirect" contract intact.
    if helpers.authentication.current_user:
        await backfill_user_timezone(helpers.authentication.current_user, helpers.connection)

    # The shell template extends no layout, so the HX-Request layout
    # auto-selection (application_layout/public_layout) is bypassed entirely —
    # this is always a full document. page_title_prefix mirrors the server's
    # format_page_title so the client useDocumentTitle hook stays in parity.
    #
    # consume_flashes=False because the shell renders no flashes: React drains them
    # from /api/users/me at boot (see AppShell). Consuming them here would destroy the
    # flash set by whatever redirected in — a sent draft, a Gmail connect.
    return helpers.render("layouts/spa.html.jinja", consume_flashes=False, page_title_prefix=page_title_prefix())


for _path, _name in SPA_ROUTES:
    # The shell handler ignores path params, so parameterized paths (e.g.
    # /documents/{document_id}) register fine — url_for fills the segment. A None
    # name falls back to the endpoint name, matching the unnamed-route default.
    router.add_api_route(_path, _render_shell, methods=["GET"], include_in_schema=False, name=_name)
