import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import HttpUrl

from app.mcp.base import mount_mcp
from config import settings


@pytest.mark.asyncio
async def test_mount_mcp_trusts_configured_hosts_and_origins():
    """FastMCP's request guard (DNS-rebinding protection, default-on since 3.4.3)
    421s any Host outside its allow-list and 403s any Origin it doesn't trust. On
    Cloud Run the socket binds to 0.0.0.0 (discarded as unspecified) and the load
    balancer forwards the public domain, so unless mount_mcp forwards our
    allowed_hosts/cors_origins every /mcp/* request — including the browser-facing
    OAuth pages — is rejected. Confirm both halves are wired through.

    The Origin half is only load-bearing because the guard reconstructs the
    request origin from the request scheme: behind a TLS-terminating load balancer
    the app sees http while the browser sent an https Origin, so that scheme
    mismatch means only our allowed_origins keeps the consent-form POST from
    403ing.
    """
    with settings.override():
        # Non-local base_url so cors_origins yields a concrete https origin rather
        # than the "*" wildcard it returns locally (which would trust everything
        # and make the origin assertions vacuous).
        settings.base_url = HttpUrl("https://convictional.test")
        settings.allowed_hosts = ["convictional.test"]

        app = FastAPI()
        async with mount_mcp(app):
            # base_url 0.0.0.0 mirrors the Cloud Run bind address into
            # scope["server"] (discarded as unspecified) and reconstructs the
            # request origin as http://… — so the explicit Host/Origin headers,
            # not the transport, drive the guard.
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://0.0.0.0:8080") as client:
                host_allowed = await client.get("/mcp/", headers={"host": "convictional.test"})
                host_blocked = await client.get("/mcp/", headers={"host": "evil.test"})
                origin_trusted = await client.get(
                    "/mcp/",
                    headers={"host": "convictional.test", "origin": "https://convictional.test"},
                )
                origin_untrusted = await client.get(
                    "/mcp/",
                    headers={"host": "convictional.test", "origin": "https://evil.test"},
                )

    # Host guard: an unknown host is blocked; the trusted public domain falls
    # through to routing/auth (any status but the 421).
    assert host_blocked.status_code == 421
    assert host_allowed.status_code != 421
    # Origin guard: our configured origin survives the http/https scheme mismatch,
    # while a foreign origin is rejected.
    assert origin_untrusted.status_code == 403
    assert origin_trusted.status_code not in (403, 421)
