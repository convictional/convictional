import pytest

from config.enums import Integration
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_chat, create_collaborator, create_user

# The canonical smallest valid VP8 WebM (185 bytes, 8x8, ~1s, from mathiasbynens/small).
# The video path DOES decode the bytes — InlineVideo swaps its <video> for a download link
# on a media error — so the fixture must be genuinely decodable or the test would silently
# exercise the file-card fallback instead of the player. The file-card test reuses these
# bytes under a non-video content_type, where they are never decoded.
VIDEO_WEBM_B64 = "GkXfo0AgQoaBAUL3gQFC8oEEQvOBCEKCQAR3ZWJtQoeBAkKFgQIYU4BnQI0VSalmQCgq17FAAw9CQE2AQAZ3aGFtbXlXQUAGd2hhbW15RIlACECPQAAAAAAAFlSua0AxrkAu14EBY8WBAZyBACK1nEADdW5khkAFVl9WUDglhohAA1ZQOIOBAeBABrCBCLqBCB9DtnVAIueBAKNAHIEAAIAwAQCdASoIAAgAAUAmJaQAA3AA/vz0AAA="  # noqa: E501


async def paste_upload(editor, filename: str, mime: str, b64: str):
    # Mirrors the attachments plugin's handlePaste: a pasted file item hits the real
    # upload endpoint and is replaced with a link node, which the compose bar unfurls.
    await editor.click()
    await editor.evaluate(
        """(el, { filename, mime, b64 }) => {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
            const file = new File([bytes], filename, { type: mime })
            const dt = new DataTransfer()
            dt.items.add(file)
            el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }))
        }""",
        {"filename": filename, "mime": mime, "b64": b64},
    )


async def open_chat_composer(browser_client: BrowserClient):
    user = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    await browser_client.login("bob@example.com")
    await browser_client.page.goto(f"{browser_client.base_url}/chats/{chat.id}")

    editor = browser_client.page.locator('.ProseMirror[contenteditable="true"]').first
    await browser_client.expect(editor).to_be_visible()
    return editor


@pytest.mark.asyncio
async def test_video_attachment_renders_inline_player(browser_client: BrowserClient):
    editor = await open_chat_composer(browser_client)
    await paste_upload(editor, "demo.webm", "video/webm", VIDEO_WEBM_B64)

    # The compose preview upgrades a video attachment to an inline <video> whose src is
    # the range-supporting download endpoint. A regression would fall back to a FileCard
    # link, so asserting the element type guards the player wiring.
    video = browser_client.page.locator("video")
    await browser_client.expect(video).to_be_visible()
    src = await video.get_attribute("src")
    assert src is not None and "/attachments/" in src and "/download" in src, src


@pytest.mark.asyncio
async def test_pdf_attachment_renders_file_card_not_player(browser_client: BrowserClient):
    editor = await open_chat_composer(browser_client)
    await paste_upload(editor, "report.pdf", "application/pdf", VIDEO_WEBM_B64)

    # A non-video attachment keeps the file-card treatment: the filename shows and no
    # <video> element is rendered.
    await browser_client.expect(browser_client.page.get_by_text("report.pdf")).to_be_visible()
    await browser_client.expect(browser_client.page.locator("video")).to_have_count(0)
