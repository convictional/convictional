from unittest.mock import AsyncMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup

from lib.unfurl import (
    UnfurlResult,
    _decode_entities,
    _find_oembed_endpoint,
    _is_cloudflare_challenge,
    _try_html_meta,
    _try_opengraph,
    is_safe_url,
    sanitize_oembed_html,
    unfurl,
)


def test_try_opengraph():
    html = """
    <html><head>
        <meta property="og:title" content="Test Article">
        <meta property="og:description" content="A test description">
        <meta property="og:image" content="https://example.com/image.jpg">
        <meta property="og:site_name" content="Example Site">
    </head></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = _try_opengraph(soup)

    assert result is not None
    assert result.title == "Test Article"
    assert result.description == "A test description"
    assert result.image_url == "https://example.com/image.jpg"
    assert result.site_name == "Example Site"


def test_try_opengraph_returns_none_without_og_title():
    html = """<html><head><meta property="og:description" content="No title"></head></html>"""
    soup = BeautifulSoup(html, "html.parser")
    assert _try_opengraph(soup) is None


def test_try_html_meta():
    html = """
    <html><head>
        <title>Fallback Title</title>
        <meta name="description" content="Fallback description">
    </head></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = _try_html_meta(soup)

    assert result is not None
    assert result.title == "Fallback Title"
    assert result.description == "Fallback description"


def test_try_html_meta_with_nothing():
    html = """<html><head></head><body>No metadata</body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    assert _try_html_meta(soup) is None


def test_is_safe_url_blocks_private_ips():
    assert not is_safe_url("http://192.168.1.1")
    assert not is_safe_url("http://10.0.0.1")
    assert not is_safe_url("http://localhost")
    assert not is_safe_url("http://127.0.0.1")
    assert not is_safe_url("http://0.0.0.0")


def test_is_safe_url_blocks_non_http():
    assert not is_safe_url("ftp://example.com")
    assert not is_safe_url("file:///etc/passwd")
    assert not is_safe_url("javascript:alert(1)")
    assert not is_safe_url("")


def test_is_safe_url_allows_valid():
    assert is_safe_url("https://example.com")
    assert is_safe_url("http://youtube.com")
    assert is_safe_url("https://www.github.com/anthropics/claude-code")


def test_find_oembed_endpoint():
    # YouTube watch URLs
    assert _find_oembed_endpoint("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is not None
    assert _find_oembed_endpoint("https://youtube.com/watch?v=dQw4w9WgXcQ") is not None
    assert _find_oembed_endpoint("http://www.youtube.com/watch?v=dQw4w9WgXcQ") is not None
    assert "url=https%3A" not in _find_oembed_endpoint("https://www.youtube.com/watch?v=abc123")  # type: ignore[operator]
    assert "youtube.com/oembed" in _find_oembed_endpoint("https://www.youtube.com/watch?v=abc123")  # type: ignore[operator]

    # YouTube watch with extra params
    assert _find_oembed_endpoint("https://www.youtube.com/watch?list=PLx&v=abc123") is not None

    # YouTube short URLs (youtu.be)
    assert _find_oembed_endpoint("https://youtu.be/dQw4w9WgXcQ") is not None
    assert _find_oembed_endpoint("http://youtu.be/dQw4w9WgXcQ") is not None

    # YouTube shorts
    assert _find_oembed_endpoint("https://www.youtube.com/shorts/abc123") is not None
    assert _find_oembed_endpoint("https://youtube.com/shorts/abc123") is not None

    # YouTube live
    assert _find_oembed_endpoint("https://www.youtube.com/live/abc123") is not None
    assert _find_oembed_endpoint("https://youtube.com/live/abc123") is not None

    # Vimeo
    endpoint = _find_oembed_endpoint("https://vimeo.com/123456789")
    assert endpoint is not None
    assert "vimeo.com/api/oembed" in endpoint
    assert _find_oembed_endpoint("https://www.vimeo.com/123456789") is not None

    # Loom
    endpoint = _find_oembed_endpoint("https://www.loom.com/share/abc123def456")
    assert endpoint is not None
    assert "loom.com/v1/oembed" in endpoint
    assert _find_oembed_endpoint("https://loom.com/share/abc123def456") is not None

    # Non-matching URLs return None
    assert _find_oembed_endpoint("https://example.com") is None
    assert _find_oembed_endpoint("https://twitter.com/user/status/123") is None
    assert _find_oembed_endpoint("https://www.youtube.com/channel/UCxyz") is None
    assert _find_oembed_endpoint("https://vimeo.com/channels/staffpicks") is None


def test_sanitize_oembed_html():
    # Safe iframe passes through with whitelisted attributes only
    safe = '<iframe src="https://youtube.com/embed/abc" width="560" height="315" allowfullscreen></iframe>'
    result = sanitize_oembed_html(safe)
    assert result is not None
    assert "<iframe" in result
    assert 'src="https://youtube.com/embed/abc"' in result
    assert "allowfullscreen" in result

    # Script tags stripped
    assert sanitize_oembed_html("<script>alert('xss')</script>") is None

    # Non-iframe HTML stripped
    assert sanitize_oembed_html("<div><p>hello</p></div>") is None

    # javascript: src stripped (only https allowed)
    result = sanitize_oembed_html('<iframe src="javascript:alert(1)"></iframe>')
    assert result is not None
    assert "javascript" not in result

    # http: src stripped (only https allowed)
    result = sanitize_oembed_html('<iframe src="http://example.com/embed"></iframe>')
    assert result is not None
    assert "http://example.com" not in result

    # Empty/whitespace returns None
    assert sanitize_oembed_html("") is None
    assert sanitize_oembed_html("   ") is None

    # Mixed content keeps only iframe
    mixed = '<iframe src="https://youtube.com/embed/abc"></iframe><script>alert(1)</script><div>text</div>'
    result = sanitize_oembed_html(mixed)
    assert result is not None
    assert "<iframe" in result
    assert "<script" not in result
    assert "<div" not in result

    # Unsafe attributes stripped from iframe
    result = sanitize_oembed_html('<iframe src="https://example.com" onload="alert(1)"></iframe>')
    assert result is not None
    assert "onload" not in result


def test_is_cloudflare_challenge():
    # CF 403 with server: cloudflare → detected
    assert _is_cloudflare_challenge(httpx.Response(status_code=403, headers={"server": "cloudflare"})) is True

    # CF 503 with server: cloudflare → detected (key case: this is what keeps a 503
    # challenge out of the 5xx failure path, so it renders a branded fallback not FAILED)
    assert _is_cloudflare_challenge(httpx.Response(status_code=503, headers={"server": "cloudflare"})) is True

    # cf-mitigated: challenge header → detected regardless of status code
    assert _is_cloudflare_challenge(httpx.Response(status_code=200, headers={"cf-mitigated": "challenge"})) is True

    # Normal 200 from Cloudflare is not a challenge
    assert _is_cloudflare_challenge(httpx.Response(status_code=200, headers={"server": "cloudflare"})) is False

    # Non-CF 403 (e.g. nginx) is not a challenge
    assert _is_cloudflare_challenge(httpx.Response(status_code=403, headers={"server": "nginx"})) is False

    # Normal 200 from non-CF server is not a challenge
    assert _is_cloudflare_challenge(httpx.Response(status_code=200, headers={"server": "nginx"})) is False


CLOUDFLARE_CHALLENGE_HTML = """
<html><head><title>Just a moment...</title></head>
<body>
<div id="challenge-running">Checking if the site connection is secure</div>
</body></html>
"""

NORMAL_HTML = """
<html><head>
<title>Welcome to Example</title>
<meta name="description" content="A real website with real content">
</head><body><p>Hello world</p></body></html>
"""


def _setup_mock_client(mock_client_cls: AsyncMock, response: httpx.Response) -> None:
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(return_value=response)
    mock_client_cls.return_value = mock_client


@pytest.mark.asyncio
@patch("lib.unfurl.httpx.AsyncClient")
async def test_unfurl_falls_back_on_cloudflare_challenges(mock_client_cls):
    # We reached the page but Cloudflare served a challenge instead of the origin.
    # Rather than nothing, return a bare result so the caller renders a branded
    # favicon + domain fallback card. No metadata is trusted from the challenge page.
    for headers in (
        {"server": "cloudflare", "cf-ray": "abc123-YYZ"},
        {"server": "cloudflare", "cf-mitigated": "challenge"},
    ):
        _setup_mock_client(
            mock_client_cls,
            httpx.Response(status_code=403, headers=headers, text=CLOUDFLARE_CHALLENGE_HTML),
        )
        result = await unfurl("https://example.com")
        assert result is not None
        assert result.title is None
        assert result.description is None
        assert result.image_url is None


@pytest.mark.asyncio
@patch("lib.unfurl.httpx.AsyncClient")
async def test_unfurl_falls_back_when_page_has_no_metadata(mock_client_cls):
    # Reached a 200 page with no OpenGraph, oEmbed, title, or description → bare
    # fallback result (branded card) rather than None.
    _setup_mock_client(
        mock_client_cls,
        httpx.Response(status_code=200, headers={"server": "nginx"}, text="<html><body>hi</body></html>"),
    )
    result = await unfurl("https://example.com")
    assert result is not None
    assert result.title is None

    # Empty body still counts as reaching the page → bare fallback.
    _setup_mock_client(
        mock_client_cls,
        httpx.Response(status_code=200, headers={"server": "nginx"}, text=""),
    )
    assert await unfurl("https://example.com") is not None


@pytest.mark.asyncio
@patch("lib.unfurl.httpx.AsyncClient")
async def test_unfurl_returns_none_on_server_error(mock_client_cls):
    # A genuine origin 5xx is transient → None so the caller marks it FAILED and
    # retries once the server recovers, rather than caching an empty preview for the TTL.
    _setup_mock_client(
        mock_client_cls,
        httpx.Response(status_code=502, headers={"server": "nginx"}, text="<html><body>bad gateway</body></html>"),
    )
    assert await unfurl("https://example.com") is None

    # A Cloudflare challenge that surfaces as 503 is not transient (retry won't clear
    # it) → branded fallback rather than FAILED.
    _setup_mock_client(
        mock_client_cls,
        httpx.Response(status_code=503, headers={"server": "cloudflare"}, text=CLOUDFLARE_CHALLENGE_HTML),
    )
    assert await unfurl("https://example.com") is not None


@pytest.mark.asyncio
@patch("lib.unfurl.httpx.AsyncClient")
async def test_unfurl_returns_none_when_fetch_fails(mock_client_cls):
    # Never reached the origin (timeout, DNS, reset) → None so the caller marks it
    # FAILED and backs off; there is no page to describe.
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client_cls.return_value = mock_client

    assert await unfurl("https://example.com") is None


def test_decode_entities():
    # Extractors single-decode (BeautifulSoup for HTML, json for oEmbed), so a
    # double-encoded CMS page leaves a literal `&#8217;` / `&amp;` in the text.
    # _decode_entities decodes the text fields once more; it leaves URLs and
    # oEmbed markup untouched (a further unescape would corrupt `&`-joined query
    # params, and the HTML is sanitized elsewhere).
    result = _decode_entities(
        UnfurlResult(
            title="Nick Hamze&#8217;s Story",
            description="It&#8217;s a &lt;test&gt;",
            site_name="Ben &amp; Jerry&#39;s",
            image_url="https://example.com/i.jpg?a=1&amp;b=2",
            oembed_type="video",
            oembed_html='<iframe src="https://example.com?a=1&amp;b=2"></iframe>',
        )
    )
    assert result.title == "Nick Hamze’s Story"
    assert result.description == "It’s a <test>"
    assert result.site_name == "Ben & Jerry's"
    assert result.image_url == "https://example.com/i.jpg?a=1&amp;b=2"
    assert result.oembed_html == '<iframe src="https://example.com?a=1&amp;b=2"></iframe>'

    # Already-plain text is a no-op: decoding is idempotent, and None fields pass through.
    plain = _decode_entities(UnfurlResult(title="It's great & cheap", description=None, site_name=None))
    assert plain.title == "It's great & cheap"
    assert plain.description is None
    assert plain.site_name is None


@pytest.mark.asyncio
@patch("lib.unfurl.httpx.AsyncClient")
async def test_unfurl_returns_result_for_non_cloudflare_responses(mock_client_cls):
    # Normal 200 from non-CF server → parsed and returned
    _setup_mock_client(
        mock_client_cls,
        httpx.Response(
            status_code=200,
            headers={"server": "nginx", "content-type": "text/html"},
            text=NORMAL_HTML,
        ),
    )
    result = await unfurl("https://example.com")
    assert result is not None
    assert result.title == "Welcome to Example"
    assert result.description == "A real website with real content"

    # Non-CF 403 (e.g. auth-gated content) → still parsed and returned
    html = """<html><head><title>Forbidden - Members Only</title>
    <meta name="description" content="You need to log in"></head></html>"""
    _setup_mock_client(
        mock_client_cls,
        httpx.Response(
            status_code=403,
            headers={"server": "nginx", "content-type": "text/html"},
            text=html,
        ),
    )
    result = await unfurl("https://members-only-site.com")
    assert result is not None
    assert result.title == "Forbidden - Members Only"
