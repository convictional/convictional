def platform_label(user_agent: str | None) -> str | None:
    """Turn a raw User-Agent into a short friendly label like 'Chrome on macOS'.

    Returns None when no token matches — the caller can fall back to whatever
    identifier it has (truncated endpoint, request id, etc.). Browser order
    matters: Edge / OPR / Chrome / Safari / Firefox. Chrome's UA contains
    'Safari' too, so we check the more specific tokens first.
    """
    if not user_agent:
        return None

    ua_lower = user_agent.lower()

    if "iphone" in ua_lower or "ipod" in ua_lower:
        os_name: str | None = "iOS"
    elif "ipad" in ua_lower:
        os_name = "iPadOS"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "mac os x" in ua_lower or "macintosh" in ua_lower:
        os_name = "macOS"
    elif "windows" in ua_lower:
        os_name = "Windows"
    elif "linux" in ua_lower:
        os_name = "Linux"
    else:
        os_name = None

    browser: str | None
    if "edg/" in ua_lower or "edge/" in ua_lower:
        browser = "Edge"
    elif "opr/" in ua_lower or "opera" in ua_lower:
        browser = "Opera"
    elif "firefox" in ua_lower or "fxios" in ua_lower:
        browser = "Firefox"
    elif "chrome/" in ua_lower or "crios" in ua_lower:
        browser = "Chrome"
    elif "safari" in ua_lower:
        browser = "Safari"
    else:
        browser = None

    if browser and os_name:
        return f"{browser} on {os_name}"
    return browser or os_name
