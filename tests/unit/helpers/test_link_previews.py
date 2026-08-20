from app.helpers.link_previews import is_internal_url
from config.settings import settings


def test_is_internal_url():
    base = str(settings.base_url).rstrip("/")
    assert is_internal_url(f"{base}/posts/abc")
    assert is_internal_url(f"{base}/goals/def")
    assert is_internal_url(base)
    assert not is_internal_url("https://github.com/anthropics")
    assert not is_internal_url("http://localhost:9999/posts/abc")
    assert not is_internal_url(f"{base}evil.com/posts/abc")
    assert not is_internal_url(f"{base}@evil.com/posts/abc")
    assert not is_internal_url("http://evil.com:8000/posts/abc")
