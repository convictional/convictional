import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { MessageBubble } from "~/react/composites/chat/MessageBubble"
import type { ChatMessage, LinkPreview } from "~/react/shared/types"

vi.mock("~/react/ui/Avatar", () => ({
  Avatar: ({ displayName }: { displayName: string }) => <div data-testid="avatar">{displayName}</div>,
}))
vi.mock("~/react/composites/UserHoverCard", () => ({
  UserHoverCard: ({ children }: { children: React.ReactNode }) => <div data-testid="user-hover-card">{children}</div>,
}))
vi.mock("~/react/composites/chat/LinkPreviewCard", () => ({
  LinkPreviewCard: () => <div data-testid="link-preview-card" />,
}))

afterEach(() => {
  cleanup()
})

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "m1",
    content: "hello",
    created_at: "2026-04-30T12:00:00Z",
    edited_at: null,
    reactions: {},
    user: { id: "u-author", display_name: "Author", picture: null },
    link_preview: null,
    reply_to: null,
    ...overrides,
  }
}

function makeLinkPreview(overrides: Partial<LinkPreview> = {}): LinkPreview {
  return {
    url: "https://x/report.pdf",
    type: "link",
    title: null,
    description: null,
    image_url: null,
    site_name: null,
    domain: "x",
    resource_kind: "file",
    file: null,
    ...overrides,
  }
}

describe("MessageBubble", () => {
  test("renders the bubble body from message.content via Markdown", () => {
    const message = makeMessage({
      content: "**bold** @[Alice]",
    })

    const { container } = render(<MessageBubble message={message} onScrollTo={vi.fn()} />)

    const strong = container.querySelector("strong")
    expect(strong?.textContent).toBe("bold")

    const mention = container.querySelector("[data-name='Alice']")
    expect(mention).not.toBeNull()
    expect(mention?.textContent).toContain("Alice")

    expect(container.textContent).not.toContain("**")
  })

  test("renders the reply preview content_preview as-is (server pre-formats it)", () => {
    const message = makeMessage({
      content: "the reply body",
      reply_to: {
        id: "r1",
        user_name: "Bob",
        content_preview: "bold link @Alice",
        is_deleted: false,
      },
    })

    render(<MessageBubble message={message} onScrollTo={vi.fn()} />)

    expect(screen.getByText("bold link @Alice")).toBeTruthy()
  })

  test("clicking the reply quote scrolls to the quoted message", () => {
    const onScrollTo = vi.fn()
    const message = makeMessage({
      reply_to: { id: "r1", user_name: "Bob", content_preview: "the quoted text", is_deleted: false },
    })

    render(<MessageBubble message={message} onScrollTo={onScrollTo} />)

    fireEvent.click(screen.getByText("the quoted text"))
    expect(onScrollTo).toHaveBeenCalledWith("r1")
  })

  test("renders a deleted quoted message as a tombstone that is still clickable", () => {
    const onScrollTo = vi.fn()
    const message = makeMessage({
      reply_to: { id: "r1", user_name: "Bob", content_preview: "", is_deleted: true },
    })

    render(<MessageBubble message={message} onScrollTo={onScrollTo} />)

    fireEvent.click(screen.getByText("This message was deleted"))
    // Chat keeps the tombstone clickable — it jumps toward where the message was.
    expect(onScrollTo).toHaveBeenCalledWith("r1")
  })

  test("shows the load-around spinner while scrolling to an off-window target", () => {
    const message = makeMessage({
      reply_to: { id: "r1", user_name: "Bob", content_preview: "the quoted text", is_deleted: false },
    })

    render(<MessageBubble message={message} onScrollTo={vi.fn()} scrollingToId="r1" />)

    expect(screen.getByText("Loading message...")).toBeTruthy()
    expect(screen.queryByText("the quoted text")).toBeNull()
  })

  test("wraps images in ChatImage so they're height-capped and click-to-lightbox", () => {
    const message = makeMessage({
      content: "look at this ![cat](https://example.com/cat.gif)",
    })

    const { container } = render(<MessageBubble message={message} onScrollTo={vi.fn()} />)

    const img = container.querySelector("img")
    expect(img).not.toBeNull()
    expect(img?.getAttribute("src")).toBe("https://example.com/cat.gif")
    // ChatImage's height-cap class is the contract that survives a refactor
    // of the styling: the image must not be allowed to render at natural size.
    expect(img?.className).toMatch(/\bmax-h-\[/)

    // Clicking the image opens the lightbox (a Dialog with a Close button).
    fireEvent.click(img!)
    expect(screen.getByLabelText("Close")).toBeInTheDocument()
  })

  test("sanitizes javascript: links from message.content (rehype-sanitize)", () => {
    const message = makeMessage({
      content: '[click me](javascript:alert("xss"))',
    })

    const { container } = render(<MessageBubble message={message} onScrollTo={vi.fn()} />)

    // rehype-sanitize must strip the javascript: href. The link text should
    // still render, but the anchor must not navigate to a javascript: URL.
    expect(container.textContent).toContain("click me")

    const anchor = container.querySelector("a")
    if (anchor) {
      expect(anchor.getAttribute("href")?.toLowerCase().startsWith("javascript:")).not.toBe(true)
    }

    expect(container.querySelector("script")).toBeNull()
    expect(container.innerHTML.toLowerCase()).not.toContain('href="javascript:')
    expect(container.innerHTML.toLowerCase()).not.toContain("href='javascript:")
  })

  test("a file attachment preview strips the duplicate inline link, leaving only the card", () => {
    const message = makeMessage({
      content: "[report.pdf](https://x/report.pdf)",
      link_preview: makeLinkPreview({ resource_kind: "file" }),
    })

    const { container } = render(<MessageBubble message={message} onScrollTo={vi.fn()} />)

    expect(screen.getByTestId("link-preview-card")).toBeTruthy()
    expect(container.querySelector("a")).toBeNull()
    expect(container.textContent).not.toContain("report.pdf")
  })

  test("a non-file preview keeps both the inline link and the card", () => {
    const message = makeMessage({
      content: "[the doc](https://x/doc)",
      link_preview: makeLinkPreview({ url: "https://x/doc", resource_kind: "document" }),
    })

    const { container } = render(<MessageBubble message={message} onScrollTo={vi.fn()} />)

    expect(screen.getByTestId("link-preview-card")).toBeTruthy()
    const anchor = container.querySelector("a")
    expect(anchor).not.toBeNull()
    expect(anchor?.textContent).toContain("the doc")
  })
})
