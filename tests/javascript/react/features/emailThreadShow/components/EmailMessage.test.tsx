import { fireEvent, screen, waitFor } from "@testing-library/react"
import type { ReactElement } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const apiFetchMock = vi.fn()
vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: (url: string, options?: RequestInit) => apiFetchMock(url, options),
}))

// Dropdown bringsalong floating-ui complexity that's not under test here.
vi.mock("~/react/ui/Dropdown", () => ({
  Dropdown: ({ children }: { children: ({ close }: { close: () => void }) => React.ReactNode }) => (
    <>{children({ close: () => {} })}</>
  ),
}))

import { EmailMessage } from "~/react/features/emailThreadShow/components/EmailMessage"
import { emailMessageContentQueryKey } from "~/react/features/emailThreadShow/queries"
import type { EmailMessageContentResponse, EmailMessageSummary } from "~/react/shared/types"

import { cleanup, createTestQueryClient, renderWithClient } from "../../../shared/testUtils"

// Each render gets its own QueryClient so per-message content cached in one test
// (["emailMessageContent", id]) doesn't leak into the next. `seed` pre-populates
// that cache to model the thread's load-time batch having already run.
function renderMessage(ui: ReactElement, seed?: EmailMessageContentResponse) {
  const client = createTestQueryClient()
  if (seed) client.setQueryData(emailMessageContentQueryKey("m1"), seed)
  return renderWithClient(ui, client)
}

const baseMessage: EmailMessageSummary = {
  id: "m1",
  message_type: "received",
  subject: "Subj",
  raw_sender: "Alice <alice@example.com>",
  sender_name: "Alice",
  sender_email: "alice@example.com",
  to: ["me@example.com"],
  cc: [],
  bcc: [],
  preview: "Preview text",
  received_at: "2026-01-01T00:00:00Z",
  sent_at: "2026-01-01T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
  external_thread_id: null,
  message_id: null,
  content_url: "/api/email_threads/T/email_messages/m1/content",
  reply_url: "/reply",
  forward_url: "/forward",
  view_original_url: "/orig",
}

// Dispatch a real bubbling keydown so @github/hotkey's document listener
// synthesizes the button click. @github/hotkey is not stubbed here.
function pressKey(key: string) {
  fireEvent.keyDown(document.body, { key })
}

afterEach(() => {
  cleanup()
})

beforeEach(() => {
  apiFetchMock.mockReset()
})

describe("EmailMessage", () => {
  it("fetches and renders the body when expanded on mount", async () => {
    apiFetchMock.mockResolvedValueOnce({
      content_html: "<p>body</p>",
      body_plain: null,
      attachments: [],
    })

    renderMessage(
      <EmailMessage
        message={baseMessage}
        isLastMessage={false}
        canReply={true}
        isSuperuser={false}
        startCollapsed={false}
        currentUserEmail="me@example.com"
        onReply={vi.fn()}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />
    )
    expect(screen.getByText("Alice")).toBeTruthy()

    // The timeline carries no body, so an expanded message fetches it from content_url.
    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(
        baseMessage.content_url,
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      )
    })
    // Body HTML lives inside a sandboxed iframe srcdoc once the fetch resolves.
    await waitFor(() => {
      const iframe = document.querySelector("iframe") as HTMLIFrameElement
      expect(iframe?.srcdoc).toContain("<p>body</p>")
    })
  })

  it("collapsed message lazy-loads content on first expand", async () => {
    apiFetchMock.mockResolvedValueOnce({
      content_html: "<p>lazy</p>",
      body_plain: null,
      attachments: [],
    })

    // The timeline carries no body; a collapsed message fetches it lazily on expand.
    renderMessage(
      <EmailMessage
        message={baseMessage}
        isLastMessage={false}
        canReply={true}
        isSuperuser={false}
        startCollapsed={true}
        currentUserEmail="me@example.com"
        onReply={vi.fn()}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />
    )

    // Collapsed preview is shown
    expect(screen.getByText("Preview text")).toBeTruthy()
    expect(apiFetchMock).not.toHaveBeenCalled()

    const header = document.querySelector('[aria-expanded="false"]') as HTMLElement
    fireEvent.click(header)

    await waitFor(() => {
      // The fetch is issued with an abort signal so it can be cancelled on unmount.
      expect(apiFetchMock).toHaveBeenCalledWith(
        baseMessage.content_url,
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      )
    })
    await waitFor(() => {
      const iframe = document.querySelector("iframe") as HTMLIFrameElement
      expect(iframe?.srcdoc).toContain("<p>lazy</p>")
    })

    // Second toggle (collapse) then re-expand should not refetch
    fireEvent.click(document.querySelector('[aria-expanded="true"]') as HTMLElement)
    fireEvent.click(document.querySelector('[aria-expanded="false"]') as HTMLElement)
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it("renders body seeded in the content cache without fetching", async () => {
    // The thread's load-time batch seeds ["emailMessageContent", id] before the
    // timeline paints, so an expanded message is a cache hit and never hits content_url.
    renderMessage(
      <EmailMessage
        message={baseMessage}
        isLastMessage={false}
        canReply={true}
        isSuperuser={false}
        startCollapsed={false}
        currentUserEmail="me@example.com"
        onReply={vi.fn()}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />,
      { content_html: "<p>batched</p>", body_plain: null, attachments: [] }
    )

    await waitFor(() => {
      const iframe = document.querySelector("iframe") as HTMLIFrameElement
      expect(iframe?.srcdoc).toContain("<p>batched</p>")
    })
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it("shows the primary action row on the last message and emits the right callback", () => {
    // Expanded on mount → the component fetches its body; resolve it so the async
    // load settles cleanly. The action row renders independently of the body.
    apiFetchMock.mockResolvedValue({ content_html: "<p>body</p>", body_plain: null, attachments: [] })
    const onReply = vi.fn()
    const onReplyAll = vi.fn()
    const onForward = vi.fn()
    renderMessage(
      <EmailMessage
        message={baseMessage}
        isLastMessage={true}
        canReply={true}
        isSuperuser={false}
        startCollapsed={false}
        currentUserEmail="me@example.com"
        onReply={onReply}
        onReplyAll={onReplyAll}
        onForward={onForward}
      />
    )
    // The primary action row buttons are rendered; the dropdown also renders
    // its own buttons (mocked above to render in-place), so use explicit
    // labels paired with data-hotkey to pick the primary row buttons.
    fireEvent.click(document.querySelector('[data-hotkey="r"]') as HTMLElement)
    fireEvent.click(document.querySelector('[data-hotkey="a"]') as HTMLElement)
    fireEvent.click(document.querySelector('[data-hotkey="f"]') as HTMLElement)
    expect(onReply).toHaveBeenCalledOnce()
    expect(onReplyAll).toHaveBeenCalledOnce()
    expect(onForward).toHaveBeenCalledOnce()
  })

  it("fires r/a/f from the keyboard on the last-message action row", async () => {
    apiFetchMock.mockResolvedValue({ content_html: "<p>body</p>", body_plain: null, attachments: [] })
    const onReply = vi.fn()
    const onReplyAll = vi.fn()
    const onForward = vi.fn()
    renderMessage(
      <EmailMessage
        message={baseMessage}
        isLastMessage={true}
        canReply={true}
        isSuperuser={false}
        startCollapsed={false}
        currentUserEmail="me@example.com"
        onReply={onReply}
        onReplyAll={onReplyAll}
        onForward={onForward}
      />
    )
    // Let the expanded last message's body fetch settle.
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())

    pressKey("r")
    expect(onReply).toHaveBeenCalledOnce()
    expect(onReply).toHaveBeenCalledWith("m1")

    pressKey("a")
    expect(onReplyAll).toHaveBeenCalledOnce()
    expect(onReplyAll).toHaveBeenCalledWith("m1")

    pressKey("f")
    expect(onForward).toHaveBeenCalledOnce()
    expect(onForward).toHaveBeenCalledWith("m1")

    // @github/hotkey's isFormField gate bails while typing in an input.
    const input = document.createElement("input")
    document.body.appendChild(input)
    input.focus()
    fireEvent.keyDown(input, { key: "r" })
    expect(onReply).toHaveBeenCalledOnce()
    document.body.removeChild(input)
  })

  it("does not fire r/a/f when not the last message", () => {
    apiFetchMock.mockResolvedValue({ content_html: "<p>body</p>", body_plain: null, attachments: [] })
    const onReply = vi.fn()
    renderMessage(
      <EmailMessage
        message={baseMessage}
        isLastMessage={false}
        canReply={true}
        isSuperuser={false}
        startCollapsed={false}
        currentUserEmail="me@example.com"
        onReply={onReply}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />
    )
    pressKey("r")
    expect(onReply).not.toHaveBeenCalled()
  })
})
