import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { ActionSheet } from "~/react/composites/ActionSheet"
import { confirm } from "~/react/composites/confirmationDialog/confirm"
import type { Decision, ReactionUser } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"

vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))
vi.mock("~/react/composites/confirmationDialog/confirm", () => ({ confirm: vi.fn() }))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

const noopHandlers = {
  onClose: vi.fn(),
  onReact: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
}

function renderSheet(props: Partial<Parameters<typeof ActionSheet>[0]> = {}) {
  return render(
    <ActionSheet
      content="hello **world**"
      author={{ id: "u-author", display_name: "Alice", picture: null }}
      createdAt="2026-04-30T12:00:00Z"
      edited={false}
      reactions={{}}
      isOwn={false}
      {...noopHandlers}
      {...props}
    />
  )
}

describe("ActionSheet content", () => {
  test("renders the body through Markdown and groups reactor names by emoji", () => {
    const reactions: Record<string, ReactionUser[]> = {
      thumbs_up: [
        { id: "u1", display_name: "Alice" },
        { id: "u2", display_name: "Bob" },
      ],
      heart: [{ id: "u3", display_name: "Carol" }],
    }
    renderSheet({ reactions })

    // The sheet renders into a FloatingPortal at the document root.
    expect(document.querySelector("strong")?.textContent).toBe("world")
    expect(screen.getByText("Alice, Bob")).toBeTruthy()
    expect(screen.getByText("Carol")).toBeTruthy()
    // Each active reaction's emoji appears in the reactor list and in the picker row.
    expect(screen.getAllByText("👍").length).toBeGreaterThanOrEqual(2)
  })

  test("omits the reactor list when no reactions exist", () => {
    renderSheet({ reactions: { thumbs_up: [] } })
    // Picker row still renders the emoji once; no reactor list means no second instance.
    expect(screen.getAllByText("👍").length).toBe(1)
  })

  test("Copy writes rendered plain text and closes; error text uses the resource label", () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } })
    const onClose = vi.fn()

    renderSheet({ content: "hello **world**", onClose })
    fireEvent.click(screen.getByRole("button", { name: "Copy" }))

    expect(writeText).toHaveBeenCalledWith("hello world")
    fireEvent.animationEnd(screen.getByRole("dialog"))
    expect(onClose).toHaveBeenCalled()
  })

  test("Copy flashes a label-specific error when the Clipboard API is unavailable", () => {
    vi.stubGlobal("navigator", { ...navigator, clipboard: undefined })

    renderSheet({ resourceLabel: "comment" })
    expect(() => fireEvent.click(screen.getByRole("button", { name: "Copy" }))).not.toThrow()
    expect(showFlash).toHaveBeenCalledWith("Couldn't copy comment", "error")
  })
})

describe("ActionSheet actions", () => {
  test("shows a Reply row only when onReply is wired", () => {
    const { rerender } = renderSheet()
    expect(screen.queryByRole("button", { name: "Reply" })).toBeNull()

    rerender(
      <ActionSheet
        content="hi"
        author={{ id: "u-author", display_name: "Alice", picture: null }}
        createdAt="2026-04-30T12:00:00Z"
        edited={false}
        reactions={{}}
        isOwn={false}
        {...noopHandlers}
        onReply={vi.fn()}
      />
    )
    expect(screen.getByRole("button", { name: "Reply" })).toBeTruthy()
  })

  test("gates Edit/Delete to the owner; Copy is always available", () => {
    const { rerender } = renderSheet({ isOwn: false })
    expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull()

    rerender(
      <ActionSheet
        content="hi"
        author={{ id: "u-author", display_name: "Alice", picture: null }}
        createdAt="2026-04-30T12:00:00Z"
        edited={false}
        reactions={{}}
        isOwn={true}
        {...noopHandlers}
      />
    )
    expect(screen.getByRole("button", { name: "Edit" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy()
  })

  test("deletes immediately when no confirmation is configured (chat)", () => {
    const onDelete = vi.fn()
    renderSheet({ isOwn: true, onDelete })

    fireEvent.click(screen.getByRole("button", { name: "Delete" }))

    expect(confirm).not.toHaveBeenCalled()
    expect(onDelete).toHaveBeenCalledOnce()
  })

  test("confirms before deleting when deleteConfirmation is set (comments)", async () => {
    vi.mocked(confirm).mockResolvedValue(true)
    const onDelete = vi.fn()
    renderSheet({ isOwn: true, onDelete, deleteConfirmation: "Delete this comment?" })

    fireEvent.click(screen.getByRole("button", { name: "Delete" }))

    expect(confirm).toHaveBeenCalledWith({ message: "Delete this comment?" })
    await vi.waitFor(() => expect(onDelete).toHaveBeenCalledOnce())
  })

  test("does not delete when the confirmation is cancelled", async () => {
    vi.mocked(confirm).mockResolvedValue(false)
    const onDelete = vi.fn()
    renderSheet({ isOwn: true, onDelete, deleteConfirmation: "Delete this comment?" })

    fireEvent.click(screen.getByRole("button", { name: "Delete" }))

    await vi.waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(onDelete).not.toHaveBeenCalled()
  })

  test("offers the decision action only when onToggleDecision is wired, with the right label", () => {
    const { rerender } = renderSheet()
    expect(screen.queryByRole("button", { name: /decision/i })).toBeNull()

    const onToggleDecision = vi.fn()
    rerender(
      <ActionSheet
        content="hi"
        author={{ id: "u-author", display_name: "Alice", picture: null }}
        createdAt="2026-04-30T12:00:00Z"
        edited={false}
        reactions={{}}
        isOwn={false}
        {...noopHandlers}
        onToggleDecision={onToggleDecision}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: "Mark as decision" }))
    expect(onToggleDecision).toHaveBeenCalledOnce()
  })

  test("shows 'Undo decision' when already decided", () => {
    const decision: Decision = {
      id: "d1",
      comment_gid: "gid://convictional/x/1",
      comment_preview: "hello",
      decided_by: null,
      decided_at: "2026-04-30T12:00:00Z",
    }
    renderSheet({ decision, onToggleDecision: vi.fn() })

    expect(screen.queryByRole("button", { name: "Mark as decision" })).toBeNull()
    expect(screen.getByRole("button", { name: "Undo decision" })).toBeTruthy()
  })
})

describe("ActionSheet dismiss + touch shield", () => {
  function getBackdrop(): HTMLElement {
    const backdrop = document.querySelector<HTMLElement>('[class*="bg-black/40"]')
    if (!backdrop) throw new Error("backdrop not found")
    return backdrop
  }

  test("a stray click on the backdrop (no preceding mousedown) does not close the sheet", () => {
    // Reproduces the iOS long-press bug: lifting the finger synthesizes a click
    // on the freshly-mounted backdrop with no mousedown of its own.
    const onClose = vi.fn()
    renderSheet({ onClose })

    fireEvent.click(getBackdrop())

    expect(onClose).not.toHaveBeenCalled()
  })

  test("keeps the pointer-blocking shield up until the originating touch lifts", () => {
    vi.useFakeTimers()
    try {
      renderSheet()

      const shield = () => document.querySelector('[class*="z-[80]"]')
      expect(shield()).toBeTruthy()

      // Holding past the old fixed timer must NOT drop the shield — the finger is
      // still down, so the synthetic click is still coming.
      act(() => {
        vi.advanceTimersByTime(1000)
      })
      expect(shield()).toBeTruthy()

      act(() => {
        window.dispatchEvent(new Event("touchend"))
      })
      act(() => {
        vi.advanceTimersByTime(100)
      })
      expect(shield()).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })
})
