import pytest

from app.helpers.url import LINKABLE_CITATION_RECORD_TYPES, citation_url, url_for_content
from app.routers.global_ids import GID_URL_REGISTRY
from tests.helpers.factories import create_content, create_organization


@pytest.mark.asyncio
async def test_citation_url():
    organization = await create_organization()

    external = await create_content(
        title="External", source_url="https://example.com/x", organization_id=organization.id
    )
    meeting = await create_content(
        title="Meeting",
        source_url="gid://convictional/Meeting/b3bc641e-1fb2-44bf-b2e0-71b01f803ab9",
        organization_id=organization.id,
    )
    email_contact = await create_content(
        title="Email Contact",
        source_url="gid://convictional/EmailContact/c0ffee00-dead-beef-cafe-000000000001",
        organization_id=organization.id,
    )
    decision = await create_content(
        title="Decision",
        source_url="gid://convictional/Decision/c0ffee00-dead-beef-cafe-000000000002",
        organization_id=organization.id,
    )
    overridden = await create_content(
        title="Overridden",
        source_url="gid://convictional/EmailContact/c0ffee00-dead-beef-cafe-000000000003",
        metadata={"url": "https://example.com/override"},
        organization_id=organization.id,
    )

    # External URLs pass through verbatim, matching url_for_content's no-request branch.
    assert citation_url(external) == "https://example.com/x"
    assert citation_url(external) == url_for_content(None, external)

    # Internal linkable gids resolve to the absolute /gid/ redirect URL.
    assert citation_url(meeting) == url_for_content(None, meeting)

    # Unlinkable internal gids return None so the citation renders as plain text.
    assert citation_url(email_contact) is None
    assert citation_url(decision) is None

    # An explicit metadata["url"] override wins even when the source gid is unlinkable,
    # matching url_for_content's precedence.
    assert citation_url(overridden) == "https://example.com/override"


def test_linkable_citation_types_are_pinned():
    # Drift guard: LINKABLE_CITATION_RECORD_TYPES is the citation gate, but the URLs are
    # resolved by GID_URL_REGISTRY in app/routers/global_ids.py. helpers/ can't import from
    # routers/ (enforced by .importlinter), so the gate is authored separately; this pins it
    # equal to the registry's keys, so adding/removing a resolver without updating the gate fails.
    registry_record_types = {record_type.__name__ for record_type in GID_URL_REGISTRY}
    assert LINKABLE_CITATION_RECORD_TYPES == registry_record_types
