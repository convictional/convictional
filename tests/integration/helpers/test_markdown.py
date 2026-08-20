import pytest

from app.helpers.markdown import MarkdownCitationFormatter
from config.settings import settings
from infra.db import GlobalID
from tests.helpers.factories import create_content, create_organization


@pytest.mark.asyncio
async def test_markdown_citation_formatter():
    organization = await create_organization()
    content_one = await create_content(
        title="First Source", source_url="https://example.com/first", organization_id=organization.id
    )
    content_two = await create_content(
        title="Second Source", source_url="https://example.com/second", organization_id=organization.id
    )
    content_three = await create_content(
        title="Third Source", source_url="https://example.com/third", organization_id=organization.id
    )
    gid_url = "gid://convictional/Meeting/b3bc641e-1fb2-44bf-b2e0-71b01f803ab9"
    gid_result = await create_content(
        title="GID Source",
        source_url=gid_url,
        organization_id=organization.id,
    )
    gid_parsed = GlobalID.parse(gid_url)
    markdown = f"""
        This is a test prompt with citations.\n\n
        Here is a citation to the first source [^content:{content_one.id}].\n\n
        Here is another citation to the second source [^content:{content_two.id}].\n\n
        And a citation to the third source [^content:{content_three.id}].\n\n
        Here's a citation that appears twice [^content:{content_one.id}].\n\n
        Here's a citation with a GID source URL [^content:{gid_result.id}].\n\n
        And a missing citation [^content:00000000-0000-0000-0000-000000000000].
    """

    results_by_id = {
        content_one.id: content_one,
        content_two.id: content_two,
        content_three.id: content_three,
        gid_result.id: gid_result,
    }
    result = MarkdownCitationFormatter(results_by_id).format(markdown)
    main_content, footnotes_section = result.rsplit("\n\n", 1) if "\n\n" in result else (result, "")
    base_url = str(settings.base_url).rstrip("/")

    # Test that duplicate citations use the same footnote number in the main content with enhanced format

    assert main_content.count("[1](https://example.com/first)") == 2
    assert main_content.count("[2](https://example.com/second)") == 1
    assert main_content.count("[3](https://example.com/third)") == 1
    assert main_content.count(f"[4]({base_url}/gid/{gid_parsed.to_param})") == 1

    # Unknown citations (no matching source) are stripped entirely, leaving no raw marker behind.
    assert "[^content:00000000-0000-0000-0000-000000000000]" not in result
    assert "[^content:" not in main_content

    # Test that we have exactly one footnote definition for each number
    assert footnotes_section.count("1.") == 1
    assert footnotes_section.count("2.") == 1
    assert footnotes_section.count("3.") == 1
    assert footnotes_section.count("4.") == 1

    # Test footnote definitions have the correct content
    assert "1. [First Source](https://example.com/first)" in footnotes_section
    assert "2. [Second Source](https://example.com/second)" in footnotes_section
    assert "3. [Third Source](https://example.com/third)" in footnotes_section
    assert f"4. [GID Source]({base_url}/gid/{gid_parsed.to_param})" in footnotes_section


@pytest.mark.asyncio
async def test_sequential_footnotes_are_comma_separated():
    organization = await create_organization()
    content_one = await create_content(
        title="First Source", source_url="https://example.com/first", organization_id=organization.id
    )
    content_two = await create_content(
        title="Second Source", source_url="https://example.com/second", organization_id=organization.id
    )

    markdown = f"Text with sequential citations[^content:{content_one.id}][^content:{content_two.id}] in one spot."

    results_by_id = {content_one.id: content_one, content_two.id: content_two}
    result = MarkdownCitationFormatter(results_by_id).format(markdown)

    assert ",</sup> <sup>" in result


@pytest.mark.asyncio
async def test_citation_formatter_renders_plain_text_for_unlinkable_sources():
    organization = await create_organization()

    unlinkable_url = "gid://convictional/EmailContact/c0ffee00-dead-beef-cafe-000000000001"
    unlinkable = await create_content(
        title="Email Contact Source", source_url=unlinkable_url, organization_id=organization.id
    )

    meeting_url = "gid://convictional/Meeting/b3bc641e-1fb2-44bf-b2e0-71b01f803ab9"
    meeting = await create_content(title="Meeting Source", source_url=meeting_url, organization_id=organization.id)
    meeting_param = GlobalID.parse(meeting_url).to_param

    external = await create_content(
        title="External Source", source_url="https://example.com/x", organization_id=organization.id
    )

    invalid_id = "00000000-0000-0000-0000-000000000000"
    markdown = (
        f"Unlinkable [^content:{unlinkable.id}]. "
        f"Meeting [^content:{meeting.id}]. "
        f"External [^content:{external.id}]. "
        f"Unlinkable again [^content:{unlinkable.id}]. "
        f"Invalid [^content:{invalid_id}]."
    )

    results_by_id = {unlinkable.id: unlinkable, meeting.id: meeting, external.id: external}
    result = MarkdownCitationFormatter(results_by_id).format(markdown)
    main_content, footnotes_section = result.rsplit("\n\n", 1) if "\n\n" in result else (result, "")
    base_url = str(settings.base_url).rstrip("/")

    # Footnote numbers follow first-appearance order: unlinkable=1, meeting=2, external=3.
    assert "<sup>[1]</sup>" in main_content
    assert "<sup>[1](" not in main_content
    assert main_content.count("[1](") == 0
    assert "/gid/" not in main_content.split("<sup>[2]")[0]

    assert "1. Email Contact Source" in footnotes_section
    assert "1. [Email Contact Source]" not in footnotes_section

    assert f"[2]({base_url}/gid/{meeting_param})" in main_content
    assert f"2. [Meeting Source]({base_url}/gid/{meeting_param})" in footnotes_section

    assert "[3](https://example.com/x)" in main_content
    assert "3. [External Source](https://example.com/x)" in footnotes_section

    # Internal gids must resolve to /gid/ links and never leak a raw gid:// token.
    assert f"{base_url}/gid/{meeting_param}" in result
    assert "gid://" not in result

    # A repeat citation reuses footnote 1; an unknown content id is removed (never left as a token).
    assert main_content.count("<sup>[1]</sup>") == 2
    assert f"[^content:{invalid_id}]" not in result
