import pytest

from config.enums import Integration
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_email_drafting(browser_client: BrowserClient):
    await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    await browser_client.login("bob@example.com")

    # Start a new thread
    compose_submit = browser_client.test_id_locator("compose-form")
    await browser_client.expect(compose_submit).to_be_visible()
    await compose_submit.click()

    # Fill in email compose form
    email_compose = browser_client.test_id_locator("email-compose")
    await browser_client.expect(email_compose).to_be_visible()

    to_field = browser_client.test_id_locator("to")
    await browser_client.expect(to_field).to_be_visible()
    await to_field.fill("alice@example.com")

    subject_field = browser_client.test_id_locator("subject")
    await browser_client.expect(subject_field).to_be_visible()
    await subject_field.fill("Hello there")

    # Fill in email body
    editor = email_compose.locator('.ProseMirror[contenteditable="true"]')
    await browser_client.expect(editor).to_be_visible()
    await browser_client.expect(editor).to_have_attribute("data-placeholder", "Compose your message...")
    await editor.type("Hello Alice")
    await editor.press("Enter")
    await editor.type("This is a test email.")
    await editor.press("Enter")
    await editor.type("Yours truly, Bob")

    # Send the email
    send_button = browser_client.test_id_locator("send-and-archive")
    await send_button.click()

    # Verify success message
    success_message = browser_client.page.locator('text="Message sent"')
    await browser_client.expect(success_message).to_be_visible()

    # Navigate to Sent folder
    filter_dropdown = browser_client.test_id_locator("inbox-filter-dropdown")
    await filter_dropdown.click()

    sent_link = browser_client.page.locator('a:has-text("Sent")')
    await browser_client.expect(sent_link).to_be_visible()
    await sent_link.click()

    # Verify email appears in Sent folder
    sent_email = browser_client.page.locator('text="Hello there"')
    await browser_client.expect(sent_email).to_be_visible()


@pytest.mark.asyncio
async def test_post_draft_markdown_formatting(browser_client: BrowserClient):
    await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    await browser_client.login("bob@example.com")

    # Navigate to posts page and expand the compose form
    await browser_client.page.goto(f"{browser_client.base_url}/posts")
    compose_editor = browser_client.page.locator('.ProseMirror[data-placeholder="Share your thoughts..."]')
    await browser_client.expect(compose_editor).to_be_visible()
    await compose_editor.click()

    # Fill in a title (now visible after expand)
    title_input = browser_client.page.locator('input[placeholder="Post title"]')
    await browser_client.expect(title_input).to_be_visible()
    await title_input.fill("Markdown Test")

    # Click "Create sharable draft" to navigate to the edit page
    draft_button = browser_client.page.get_by_role("button", name="Create sharable draft")
    await draft_button.click()
    await browser_client.page.wait_for_url("**/posts/*/edit", wait_until="domcontentloaded")

    # Find the ProseMirror editor in the draft editor
    editor = browser_client.page.locator('#post-draft .ProseMirror[contenteditable="true"]')
    await browser_client.expect(editor).to_be_visible()
    await editor.click()

    # Type **bold** followed by space — input rule should convert to bold
    await editor.type("**bold**")
    await editor.press("Space")

    # Verify bold formatting was applied
    bold_element = editor.locator("strong")
    await browser_client.expect(bold_element).to_be_visible()
    await browser_client.expect(bold_element).to_have_text("bold")

    # Press Enter, then type *italic* followed by space
    await editor.press("Enter")
    await editor.type("*italic*")
    await editor.press("Space")

    # Verify italic formatting was applied
    italic_element = editor.locator("em")
    await browser_client.expect(italic_element).to_be_visible()
    await browser_client.expect(italic_element).to_have_text("italic")
