from urllib.parse import urlparse

from config.settings import settings


def is_internal_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        base = urlparse(str(settings.base_url))
        return parsed.scheme == base.scheme and parsed.hostname == base.hostname and parsed.port == base.port
    except Exception:
        return False
