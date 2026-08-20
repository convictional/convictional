import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ReplyQuote } from "~/react/composites/comment/ReplyQuote"

afterEach(cleanup)

const base = { id: "target-c", user_name: "Alice", content_preview: "the quoted text", is_deleted: false }

describe("ReplyQuote", () => {
  it("renders the author + preview and scrolls to the target on click", () => {
    const onScrollTo = vi.fn()
    render(<ReplyQuote replyTo={base} onScrollTo={onScrollTo} />)
    expect(screen.getByText("Alice")).toBeTruthy()
    fireEvent.click(screen.getByText("the quoted text"))
    expect(onScrollTo).toHaveBeenCalledWith("target-c")
  })

  it("renders a deleted target as a non-interactive tombstone", () => {
    const onScrollTo = vi.fn()
    const { container } = render(<ReplyQuote replyTo={{ ...base, is_deleted: true }} onScrollTo={onScrollTo} />)
    expect(screen.getByText("This message was deleted")).toBeTruthy()
    // No button — a soft-deleted target isn't in the timeline to scroll to.
    expect(container.querySelector("button")).toBeNull()
  })

  it("renders a loading state in place of the preview when loading", () => {
    const onScrollTo = vi.fn()
    render(<ReplyQuote replyTo={base} onScrollTo={onScrollTo} loading />)
    expect(screen.getByText("Loading message...")).toBeTruthy()
    expect(screen.queryByText("the quoted text")).toBeNull()
  })

  it("keeps a deleted target clickable when deletedClickable is set (chat behavior)", () => {
    const onScrollTo = vi.fn()
    render(<ReplyQuote replyTo={{ ...base, is_deleted: true }} onScrollTo={onScrollTo} deletedClickable />)
    expect(screen.getByText("This message was deleted")).toBeTruthy()
    fireEvent.click(screen.getByText("This message was deleted"))
    expect(onScrollTo).toHaveBeenCalledWith("target-c")
  })
})
