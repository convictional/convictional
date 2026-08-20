import html
import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
import nh3
from bs4 import BeautifulSoup

FETCH_TIMEOUT = 5.0
# Present as a real Chrome rather than a self-identifying bot: many sites gate
# link-preview scrapers on the User-Agent, and a plausible browser fingerprint
# (UA + client hints + Sec-Fetch metadata) clears the softer bot filters.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
FETCH_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="125", "Not.A/Brand";v="24", "Google Chrome";v="125"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
OEMBED_ALLOWED_TAGS = {"iframe"}
OEMBED_ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "iframe": {"src", "width", "height", "frameborder", "allow", "allowfullscreen", "referrerpolicy", "title"},
}
OEMBED_ALLOWED_SCHEMES = {"https"}

_OEMBED_PROVIDERS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"https?://(?:www\.)?youtube\.com/watch\?.*v=[\w-]+"),
        "https://www.youtube.com/oembed?url={url}&format=json",
    ),
    (
        re.compile(r"https?://(?:www\.)?youtube\.com/shorts/[\w-]+"),
        "https://www.youtube.com/oembed?url={url}&format=json",
    ),
    (
        re.compile(r"https?://(?:www\.)?youtube\.com/live/[\w-]+"),
        "https://www.youtube.com/oembed?url={url}&format=json",
    ),
    (re.compile(r"https?://youtu\.be/[\w-]+"), "https://www.youtube.com/oembed?url={url}&format=json"),
    (re.compile(r"https?://(?:www\.)?vimeo\.com/\d+"), "https://vimeo.com/api/oembed.json?url={url}"),
    (re.compile(r"https?://(?:www\.)?loom\.com/share/[\w-]+"), "https://www.loom.com/v1/oembed?url={url}"),
]


@dataclass
class UnfurlResult:
    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    site_name: str | None = None
    oembed_type: str | None = None
    oembed_html: str | None = None


def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.hostname:
            return False
        if parsed.hostname in BLOCKED_HOSTS:
            return False
        try:
            ip = ipaddress.ip_address(parsed.hostname)
            if ip.is_private or ip.is_loopback or ip.is_reserved:
                return False
        except ValueError:
            pass
        return True
    except Exception:
        return False


def sanitize_oembed_html(html: str) -> str | None:
    cleaned = nh3.clean(
        html,
        tags=OEMBED_ALLOWED_TAGS,
        attributes=OEMBED_ALLOWED_ATTRIBUTES,
        url_schemes=OEMBED_ALLOWED_SCHEMES,
    )
    return cleaned if "<iframe" in cleaned else None


def _find_oembed_endpoint(url: str) -> str | None:
    for pattern, endpoint_template in _OEMBED_PROVIDERS:
        if pattern.fullmatch(url):
            return endpoint_template.format(url=url)
    return None


async def _try_known_oembed(client: httpx.AsyncClient, url: str) -> UnfurlResult | None:
    endpoint = _find_oembed_endpoint(url)
    if not endpoint:
        return None

    try:
        response = await client.get(endpoint)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    oembed_html = sanitize_oembed_html(data.get("html", "")) if data.get("type") == "video" else None

    return UnfurlResult(
        title=data.get("title"),
        image_url=data.get("thumbnail_url"),
        site_name=data.get("provider_name"),
        oembed_type=data.get("type"),
        oembed_html=oembed_html,
    )


def _is_cloudflare_challenge(response: httpx.Response) -> bool:
    # Cloudflare sets this header when it serves a challenge page instead of the origin response
    if response.headers.get("cf-mitigated") == "challenge":
        return True

    if response.headers.get("server", "").lower() == "cloudflare" and response.status_code in (403, 503):
        return True

    return False


def _decode_entities(result: UnfurlResult) -> UnfurlResult:
    # CMS pages (notably WordPress og: tags) double-encode entities; BeautifulSoup
    # decodes only once, leaving a literal entity in the extracted text. Decode
    # again so stored metadata is plain text.
    if result.title:
        result.title = html.unescape(result.title)
    if result.description:
        result.description = html.unescape(result.description)
    if result.site_name:
        result.site_name = html.unescape(result.site_name)
    return result


async def unfurl(url: str) -> UnfurlResult | None:
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
            headers=FETCH_HEADERS,
        ) as client:
            result = await _try_known_oembed(client, url)
            if result:
                return _decode_entities(result)

            try:
                response = await client.get(url)
            except httpx.HTTPError:
                # Never reached the origin (timeout, DNS, connection reset). There is no
                # page to describe, so signal failure and let the caller back off.
                return None

            result = await _extract_metadata(client, response)
            if result:
                return _decode_entities(result)

            # A genuine origin 5xx is transient: signal failure so the caller stores
            # FAILED and retries once the server recovers, rather than caching an empty
            # preview for the full TTL. A Cloudflare challenge can also surface as 503,
            # but it won't clear on retry, so it falls through to the branded fallback.
            if response.status_code >= 500 and not _is_cloudflare_challenge(response):
                return None

            # We reached the page but extracted nothing usable — most often a
            # Cloudflare/bot challenge, the dominant cause of empty previews. Return a
            # bare result so the card still renders a branded favicon + domain fallback
            # (both derived from the URL) instead of showing nothing.
            return UnfurlResult()

    except Exception:
        return None


async def _extract_metadata(client: httpx.AsyncClient, response: httpx.Response) -> UnfurlResult | None:
    if _is_cloudflare_challenge(response) or response.status_code >= 500 or not response.text:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    return (await _try_oembed(client, soup)) or _try_opengraph(soup) or _try_html_meta(soup)


async def _try_oembed(client: httpx.AsyncClient, soup: BeautifulSoup) -> UnfurlResult | None:
    oembed_link = soup.find("link", type="application/json+oembed")
    if not oembed_link or not hasattr(oembed_link, "get"):
        return None
    href = oembed_link.get("href")
    if not href or not isinstance(href, str) or not is_safe_url(href):
        return None

    try:
        oembed_response = await client.get(href)
        oembed_response.raise_for_status()
        data = oembed_response.json()
    except (httpx.HTTPError, ValueError):
        return None

    oembed_html = sanitize_oembed_html(data.get("html", "")) if data.get("type") == "video" else None

    return UnfurlResult(
        title=data.get("title"),
        image_url=data.get("thumbnail_url"),
        site_name=data.get("provider_name"),
        oembed_type=data.get("type"),
        oembed_html=oembed_html,
    )


def _try_opengraph(soup: BeautifulSoup) -> UnfurlResult | None:
    og_title = _meta_content(soup, property="og:title")
    if not og_title:
        return None

    return UnfurlResult(
        title=og_title,
        description=_meta_content(soup, property="og:description"),
        image_url=_meta_content(soup, property="og:image"),
        site_name=_meta_content(soup, property="og:site_name"),
    )


def _try_html_meta(soup: BeautifulSoup) -> UnfurlResult | None:
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    description = _meta_content(soup, attrs={"name": "description"})

    if not title and not description:
        return None

    return UnfurlResult(title=title, description=description)


def _meta_content(soup: BeautifulSoup, **kwargs) -> str | None:
    tag = soup.find("meta", **kwargs)
    if tag and hasattr(tag, "get"):
        content = tag.get("content")
        if isinstance(content, str):
            return content
    return None
