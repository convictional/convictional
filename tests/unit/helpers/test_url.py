from fastapi import FastAPI
from starlette.requests import Request

from app.helpers.url import BACK_LABELS, back_navigation, build_safe_redirect_url


def _request_with_query(query_string: str) -> Request:
    """Build a Starlette Request with a FastAPI app attached so url_for() works."""
    app = FastAPI()

    @app.get("/search", name="search_index")
    async def search_index(): ...

    @app.get("/documents", name="documents_index")
    async def documents_index(): ...

    @app.get("/posts", name="posts_index")
    async def posts_index(): ...

    @app.get("/", name="mailbox_index")
    async def mailbox_index(): ...

    @app.get("/unread", name="mailbox_unread")
    async def mailbox_unread(): ...

    @app.get("/archived", name="mailbox_archived")
    async def mailbox_archived(): ...

    @app.get("/sent", name="mailbox_sent")
    async def mailbox_sent(): ...

    @app.get("/snoozed", name="mailbox_snoozed")
    async def mailbox_snoozed(): ...

    @app.get("/drafts", name="mailbox_drafts")
    async def mailbox_drafts(): ...

    @app.get("/assigned_to_me", name="mailbox_assigned_to_me")
    async def mailbox_assigned_to_me(): ...

    @app.get("/goals", name="goals_index")
    async def goals_index(): ...

    @app.get("/chats", name="chats_index")
    async def chats_index(): ...

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/details",
        "raw_path": b"/details",
        "query_string": query_string.encode(),
        "headers": [(b"host", b"testserver")],
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "app": app,
        "router": app.router,
    }
    return Request(scope)


def test_build_safe_redirect_url_accepts_relative_paths():
    assert build_safe_redirect_url("/search") == "/search"
    assert build_safe_redirect_url("/search?q=foo") == "/search?q=foo"
    assert build_safe_redirect_url("/documents?q=foo#section") == "/documents?q=foo#section"


def test_build_safe_redirect_url_strips_host_from_absolute_urls():
    # Absolute URLs have their host stripped; path + query + fragment land back on our origin.
    assert build_safe_redirect_url("https://evil.com/path") == "/path"
    assert build_safe_redirect_url("//evil.com/path") == "/path"


def test_build_safe_redirect_url_strips_pagination_cursor():
    # Cursor is a transport-only param for AJAX pagination; it must not survive
    # into a back/redirect URL or the browser parks on a paginated address.
    assert build_safe_redirect_url("/?cursor=abc") == "/"
    assert build_safe_redirect_url("/inbox?cursor=abc&sort=newest") == "/inbox?sort=newest"
    assert build_safe_redirect_url("/inbox?sort=newest&cursor=abc") == "/inbox?sort=newest"
    assert build_safe_redirect_url("https://evil.com/inbox?cursor=abc") == "/inbox"


def test_build_safe_redirect_url_rejects_non_path_schemes_and_empty():
    assert build_safe_redirect_url("javascript:alert(1)") is None
    assert build_safe_redirect_url("") is None
    assert build_safe_redirect_url(None) is None


def test_back_navigation_falls_back_when_no_return_to():
    request = _request_with_query("")
    result = back_navigation(request, fallback_route="documents_index")
    assert result["url"].endswith("/documents")
    assert result["label"] == "Back to documents"


def test_back_navigation_falls_back_for_external_return_to():
    # External URL gets sanitized to /foo which matches no index, so we fall back.
    request = _request_with_query("return_to=https://evil.com/foo")
    result = back_navigation(request, fallback_route="posts_index")
    assert result["url"].endswith("/posts")
    assert result["label"] == "Back to posts"


def test_back_navigation_falls_back_for_non_path_return_to():
    request = _request_with_query("return_to=javascript:alert(1)")
    result = back_navigation(request, fallback_route="posts_index")
    assert result["url"].endswith("/posts")
    assert result["label"] == "Back to posts"


def test_back_navigation_returns_safe_return_to_and_matched_label():
    request = _request_with_query("return_to=/search?q=foo")
    result = back_navigation(request, fallback_route="documents_index")
    assert result["url"] == "/search?q=foo"
    assert result["label"] == "Back to search"


def test_back_navigation_matches_index_with_query_params():
    request = _request_with_query("return_to=/documents?filter=active")
    result = back_navigation(request, fallback_route="search_index")
    assert result["url"] == "/documents?filter=active"
    assert result["label"] == "Back to documents"


def test_back_navigation_strips_cursor_from_return_to():
    # Pagination AJAX requests cause the inbox template to render entry hrefs
    # with return_to=/inbox?cursor=abc; back_navigation must drop the cursor so
    # clicking "Back" doesn't put the user on a paginated URL.
    request = _request_with_query("return_to=%2F%3Fcursor%3Dabc%26sort%3Dnewest")
    result = back_navigation(request, fallback_route="documents_index")
    assert result["url"] == "/?sort=newest"
    assert result["label"] == "Back to inbox"


def test_back_navigation_falls_back_when_return_to_matches_no_known_index():
    request = _request_with_query("return_to=/obscure/elsewhere")
    result = back_navigation(request, fallback_route="goals_index")
    assert result["url"].endswith("/goals")
    assert result["label"] == "Back to goals"


def test_back_navigation_prefers_longest_matching_prefix():
    # mailbox_index is mounted at "/" which matches everything; a more specific index must win.
    request = _request_with_query("return_to=/chats?foo=bar")
    result = back_navigation(request, fallback_route="documents_index")
    assert result["url"] == "/chats?foo=bar"
    assert result["label"] == "Back to chats"


def test_back_labels_has_expected_routes():
    assert set(BACK_LABELS.keys()) == {
        "search_index",
        "documents_index",
        "posts_index",
        "mailbox_index",
        "mailbox_unread",
        "mailbox_archived",
        "mailbox_sent",
        "mailbox_snoozed",
        "mailbox_drafts",
        "mailbox_assigned_to_me",
        "goals_index",
        "chats_index",
        "meetings_index",
    }


def test_back_navigation_mailbox_sub_routes_keep_their_specific_labels():
    # Regression: previously /archived fell back to / with "Back to email" because
    # the path-match loop only knew about mailbox_index. Each sub-route now has
    # its own label entry.
    for path, expected_label in [
        ("/unread", "Back to unread"),
        ("/archived", "Back to archived"),
        ("/sent", "Back to sent"),
        ("/snoozed", "Back to snoozed"),
        ("/drafts", "Back to drafts"),
        ("/assigned_to_me", "Back to assigned"),
    ]:
        request = _request_with_query(f"return_to={path}")
        result = back_navigation(request, fallback_route="mailbox_index")
        assert result["url"] == path
        assert result["label"] == expected_label


def test_back_navigation_mailbox_custom_views_use_generic_label():
    # Custom views (template or saved) live at the inbox path; label them
    # distinctly instead of "Back to inbox".
    for query, label in [
        ("mailbox_view_template=urgent_important", "Back to custom view"),
        ("mailbox_view_template=by_goals", "Back to custom view"),
        ("mailbox_view_id=abc-123", "Back to custom view"),
        ("sort=oldest", "Back to inbox"),  # Plain sort on inbox stays "Back to inbox".
    ]:
        request = _request_with_query(f"return_to=/?{query}")
        result = back_navigation(request, fallback_route="mailbox_index")
        assert result["url"] == f"/?{query}"
        assert result["label"] == label
