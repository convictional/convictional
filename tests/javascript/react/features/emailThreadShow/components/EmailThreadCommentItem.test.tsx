import { act, cleanup, fireEvent, render, screen } from "../../../shared/testUtils"
import { afterEach, describe, expect, it, vi } from "vitest"

// Stub the heavy editor + reactions children so this test stays focused on the
// item's own rendering (author, edited badge, menu gating, edit toggle).
vi.mock("~/react/features/emailThreadShow/components/EmailThreadCommentEditor", () => ({
  EmailThreadCommentEditor: ({ onSave, onCancel }: { onSave: (c: string) => void; onCancel: () => void }) => (
    <div data-testid="editor">
      <button type="button" onClick={() => onSave("new body")}>
        save-edit
      </button>
      <button type="button" onClick={onCancel}>
        cancel-edit
      </button>
    </div>
  ),
}))

vi.mock("~/react/composites/reactions/Reactions", () => ({
  Reactions: () => <div data-testid="reactions" />,
}))

vi.mock("~/react/composites/reactions/ReactionChips", () => ({
  ReactionChips: () => <div data-testid="reaction-chips" />,
}))

vi.mock("~/react/composites/ActionSheet", () => ({
  ActionSheet: () => <div data-testid="action-sheet" />,
}))

vi.mock("~/react/features/emailThreadShow/components/EmailThreadCommentMenu", () => ({
  EmailThreadCommentMenu: ({ onEdit }: { onEdit: () => void }) => (
    <button type="button" data-testid="menu" onClick={onEdit}>
      menu
    </button>
  ),
}))

vi.mock("~/react/ui/DateTime", () => ({ DateTime: () => <span />, formatDateTime: () => "Jan 2 2026, 12:00 AM" }))
vi.mock("~/react/ui/Avatar", () => ({ Avatar: () => <span /> }))

import { EmailThreadCommentItem } from "~/react/features/emailThreadShow/components/EmailThreadCommentItem"
import type { Decision, EmailThreadComment } from "~/react/shared/types"

function comment(overrides: Partial<EmailThreadComment> = {}): EmailThreadComment {
  return {
    id: "c1",
    global_id: "gid://convictional/EmailThreadComment/c1",
    content: "Hello **world**",
    user: { id: "author", display_name: "Alice", picture: null },
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    reactions: {},
    link_preview: null,
    attachments: [],
    reply_to: null,
    ...overrides,
  }
}

function renderItem(
  c: EmailThreadComment,
  currentUserId: string | null,
  decision?: Decision,
  highlighted = false,
  isEditing = false
) {
  const onToggleDecision = vi.fn().mockResolvedValue(undefined)
  const onStartEdit = vi.fn()
  const onEndEdit = vi.fn()
  const utils = render(
    <EmailThreadCommentItem
      comment={c}
      currentUserId={currentUserId}
      workspaceId="w1"
      decision={decision}
      highlighted={highlighted}
      isEditing={isEditing}
      onStartEdit={onStartEdit}
      onEndEdit={onEndEdit}
      onEdit={vi.fn().mockResolvedValue(undefined)}
      onDelete={vi.fn().mockResolvedValue(undefined)}
      onToggleReaction={vi.fn().mockResolvedValue(undefined)}
      onToggleDecision={onToggleDecision}
      onScrollToComment={vi.fn()}
    />
  )
  return { ...utils, onToggleDecision, onStartEdit, onEndEdit }
}

afterEach(cleanup)

describe("EmailThreadCommentItem", () => {
  it("renders content and author, and gates the menu to the author", () => {
    const { rerender } = renderItem(comment(), "author")
    expect(screen.getByText("Alice")).toBeTruthy()
    expect(screen.getByText("world")).toBeTruthy()
    expect(screen.getByTestId("menu")).toBeTruthy()

    rerender(
      <EmailThreadCommentItem
        comment={comment()}
        currentUserId="someone-else"
        workspaceId="w1"
        decision={undefined}
        highlighted={false}
        isEditing={false}
        onStartEdit={vi.fn()}
        onEndEdit={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleReaction={vi.fn()}
        onToggleDecision={vi.fn()}
        onScrollToComment={vi.fn()}
      />
    )
    expect(screen.queryByTestId("menu")).toBeNull()
  })

  it("flashes a highlight outline when deep-linked", () => {
    const { container, rerender } = renderItem(comment(), "author", undefined, false)
    const row = () => container.querySelector('[data-comment-id="c1"]')
    expect(row()?.className).not.toContain("outline")

    rerender(
      <EmailThreadCommentItem
        comment={comment()}
        currentUserId="author"
        workspaceId="w1"
        decision={undefined}
        highlighted={true}
        isEditing={false}
        onStartEdit={vi.fn()}
        onEndEdit={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleReaction={vi.fn()}
        onToggleDecision={vi.fn()}
        onScrollToComment={vi.fn()}
      />
    )
    expect(row()?.className).toContain("outline")
  })

  it("shows the (edited) badge only when updated_at trails created_at by more than 10s", () => {
    const { unmount } = renderItem(comment({ updated_at: "2026-01-01T00:00:05Z" }), "author")
    expect(screen.queryByText("(edited)")).toBeNull()
    unmount()

    renderItem(comment({ updated_at: "2026-01-01T00:00:30Z" }), "author")
    expect(screen.getByText("(edited)")).toBeTruthy()
  })

  it("renders the editor from the controlled isEditing prop and routes edit callbacks", () => {
    // Edit mode is controlled by the parent (EmailThreadShow owns the selection
    // so the composer's Up-arrow can drive it). The menu only requests edit; the
    // editor swaps in when isEditing flips true.
    const onStartEdit = vi.fn()
    const onEndEdit = vi.fn()
    const props = {
      comment: comment(),
      currentUserId: "author",
      workspaceId: "w1",
      decision: undefined,
      highlighted: false,
      onStartEdit,
      onEndEdit,
      onEdit: vi.fn().mockResolvedValue(undefined),
      onDelete: vi.fn(),
      onToggleReaction: vi.fn(),
      onToggleDecision: vi.fn(),
      onScrollToComment: vi.fn(),
    }
    const { rerender } = render(<EmailThreadCommentItem {...props} isEditing={false} />)
    expect(screen.queryByTestId("editor")).toBeNull()

    fireEvent.click(screen.getByTestId("menu"))
    expect(onStartEdit).toHaveBeenCalledWith("c1")
    // Still not editing — the parent hasn't flipped isEditing yet.
    expect(screen.queryByTestId("editor")).toBeNull()

    rerender(<EmailThreadCommentItem {...props} isEditing={true} />)
    expect(screen.getByTestId("editor")).toBeTruthy()
    // Reactions hide while editing.
    expect(screen.queryByTestId("reactions")).toBeNull()

    fireEvent.click(screen.getByText("cancel-edit"))
    expect(onEndEdit).toHaveBeenCalledOnce()
  })

  it("scrolls into view when it enters edit mode", () => {
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView

    const { rerender } = renderItem(comment(), "author", undefined, false, false)
    expect(scrollIntoView).not.toHaveBeenCalled()

    rerender(
      <EmailThreadCommentItem
        comment={comment()}
        currentUserId="author"
        workspaceId="w1"
        decision={undefined}
        highlighted={false}
        isEditing={true}
        onStartEdit={vi.fn()}
        onEndEdit={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleReaction={vi.fn()}
        onToggleDecision={vi.fn()}
        onScrollToComment={vi.fn()}
      />
    )
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest", behavior: "smooth" })
  })

  // The migration moved comment rendering from the server-sanitized Jinja
  // partial to the React side. This guards that the comment body still flows
  // through the sanitizer-aware <Markdown> renderer (which strips dangerous
  // markup — see composites/markdown/Markdown.test.tsx) rather than any raw
  // dangerouslySetInnerHTML path. Markdown is intentionally NOT mocked in this
  // file so the real sanitizer runs here.
  it("renders a malicious comment body through the sanitizer, never as live markup", () => {
    const { container } = renderItem(
      comment({
        content: "Hi <script>alert('xss')</script> <img src=\"x\" onerror=\"alert('xss')\"> there",
      }),
      "author"
    )

    expect(container.querySelector("script")).toBeNull()
    const html = container.innerHTML.toLowerCase()
    expect(html).not.toContain("<script")
    expect(html).not.toContain("onerror")
    // The surrounding plain text still renders — sanitizing strips the payload,
    // it doesn't blank the comment.
    expect(container.textContent).toContain("there")
  })

  it("strips the duplicate inline link for a file attachment preview, leaving only the card", () => {
    const { container } = renderItem(
      comment({
        content: "[report.pdf](https://x/report.pdf)",
        link_preview: {
          url: "https://x/report.pdf",
          title: null,
          description: null,
          image_url: null,
          resource_kind: "file",
          file: null,
        },
      }),
      "author"
    )
    const scope = container.querySelector('[data-comment-id="c1"]')!
    // Only the file card's download anchor survives; the inline [report.pdf] link is gone.
    const anchors = scope.querySelectorAll("a")
    expect(anchors.length).toBe(1)
    expect(anchors[0].getAttribute("href")).toBe("https://x/report.pdf")
    expect(scope.textContent).not.toContain("report.pdf")
  })

  it("keeps both the inline link and the card for a non-file preview", () => {
    renderItem(
      comment({
        content: "[the doc](https://x/doc)",
        link_preview: {
          url: "https://x/doc",
          title: null,
          description: null,
          image_url: null,
          resource_kind: "document",
          file: null,
        },
      }),
      "author"
    )
    // The inline link is preserved for non-file previews (scoping guard).
    expect(screen.getByText("the doc")).toBeInTheDocument()
  })

  describe("mobile (touch)", () => {
    afterEach(() => {
      delete document.documentElement.dataset.isMobile
    })

    function setMobile() {
      document.documentElement.dataset.isMobile = "true"
    }

    it("hides the hover overflow menu on mobile — actions move to the long-press sheet", () => {
      setMobile()
      renderItem(comment(), "author")
      expect(screen.queryByTestId("menu")).toBeNull()
    })

    it("opens the action sheet after a long press", () => {
      vi.useFakeTimers()
      try {
        setMobile()
        const { container } = renderItem(comment(), "author")
        const row = container.querySelector('[data-comment-id="c1"]') as HTMLElement

        expect(screen.queryByTestId("action-sheet")).toBeNull()

        fireEvent.touchStart(row)
        // useLongPress fires onLongPress at its 500ms threshold.
        act(() => {
          vi.advanceTimersByTime(500)
        })

        expect(screen.getByTestId("action-sheet")).toBeTruthy()
      } finally {
        vi.useRealTimers()
      }
    })
  })

  describe("quote-reply", () => {
    const replyTo = {
      id: "target-c",
      user_name: "Bob",
      content_preview: "the quoted line",
      is_deleted: false,
    }

    it("opens a reply quoting this comment from the desktop hover affordance", () => {
      const onReply = vi.fn()
      render(
        <EmailThreadCommentItem
          comment={comment({ content: "Hello **world**" })}
          currentUserId="author"
          workspaceId="w1"
          decision={undefined}
          highlighted={false}
          isEditing={false}
          onStartEdit={vi.fn()}
          onEndEdit={vi.fn()}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
          onToggleReaction={vi.fn()}
          onToggleDecision={vi.fn()}
          onReply={onReply}
          onScrollToComment={vi.fn()}
        />
      )
      fireEvent.click(screen.getByLabelText("Reply"))
      // The preview is built from the comment: author + plain-text (markdown stripped).
      expect(onReply).toHaveBeenCalledWith({
        id: "c1",
        user_name: "Alice",
        content_preview: "Hello world",
        is_deleted: false,
      })
    })

    it("renders a live quote that scrolls to its target on click", () => {
      const onScrollToComment = vi.fn()
      render(
        <EmailThreadCommentItem
          comment={comment({ reply_to: replyTo })}
          currentUserId="author"
          workspaceId="w1"
          decision={undefined}
          highlighted={false}
          isEditing={false}
          onStartEdit={vi.fn()}
          onEndEdit={vi.fn()}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
          onToggleReaction={vi.fn()}
          onToggleDecision={vi.fn()}
          onScrollToComment={onScrollToComment}
        />
      )
      expect(screen.getByText("the quoted line")).toBeTruthy()
      fireEvent.click(screen.getByText("the quoted line"))
      expect(onScrollToComment).toHaveBeenCalledWith("target-c")
    })

    it("renders a deleted target as an inert tombstone (no scroll)", () => {
      const onScrollToComment = vi.fn()
      const { container } = render(
        <EmailThreadCommentItem
          comment={comment({ reply_to: { ...replyTo, is_deleted: true } })}
          currentUserId="author"
          workspaceId="w1"
          decision={undefined}
          highlighted={false}
          isEditing={false}
          onStartEdit={vi.fn()}
          onEndEdit={vi.fn()}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
          onToggleReaction={vi.fn()}
          onToggleDecision={vi.fn()}
          onScrollToComment={onScrollToComment}
        />
      )
      expect(screen.getByText("This message was deleted")).toBeTruthy()
      // The tombstone is not a button — nothing to navigate to.
      const scope = container.querySelector('[data-comment-id="c1"]')!
      const replyButtons = Array.from(scope.querySelectorAll("button")).filter(b =>
        b.textContent?.includes("This message was deleted")
      )
      expect(replyButtons).toHaveLength(0)
    })
  })

  describe("swipe-to-reply (mobile)", () => {
    afterEach(() => {
      delete document.documentElement.dataset.isMobile
    })

    function setMobile() {
      document.documentElement.dataset.isMobile = "true"
    }

    function touches(x: number, y: number) {
      return { touches: [{ clientX: x, clientY: y }] }
    }

    function renderWithReply(onReply: (preview: unknown) => void, mobile: boolean) {
      if (mobile) setMobile()
      const { container } = render(
        <EmailThreadCommentItem
          comment={comment({ content: "Hello **world**" })}
          currentUserId="author"
          workspaceId="w1"
          decision={undefined}
          highlighted={false}
          isEditing={false}
          onStartEdit={vi.fn()}
          onEndEdit={vi.fn()}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
          onToggleReaction={vi.fn()}
          onToggleDecision={vi.fn()}
          onReply={onReply}
          onScrollToComment={vi.fn()}
        />
      )
      return container.querySelector('[data-comment-id="c1"]') as HTMLElement
    }

    it("commits a reply quoting this comment on a left swipe past the threshold", () => {
      const onReply = vi.fn()
      const row = renderWithReply(onReply, true)

      fireEvent.touchStart(row, touches(200, 100))
      fireEvent.touchMove(row, touches(110, 100)) // dx = -90 → pull past the trigger
      fireEvent.touchEnd(row)

      expect(onReply).toHaveBeenCalledWith({
        id: "c1",
        user_name: "Alice",
        content_preview: "Hello world",
        is_deleted: false,
      })
    })

    it("does not arm the swipe on desktop (no touch pointer)", () => {
      const onReply = vi.fn()
      const row = renderWithReply(onReply, false)

      fireEvent.touchStart(row, touches(200, 100))
      fireEvent.touchMove(row, touches(110, 100))
      fireEvent.touchEnd(row)

      expect(onReply).not.toHaveBeenCalled()
    })

    it("does not swipe-reply while the comment is being edited", () => {
      // The editor renders inside the swipe root; a drag over it must not commit a
      // reply (which would discard the unsaved edit). The ref is swapped off the
      // swipe hook in edit mode, so the listeners are never bound.
      setMobile()
      const onReply = vi.fn()
      const { container } = render(
        <EmailThreadCommentItem
          comment={comment({ content: "Hello **world**" })}
          currentUserId="author"
          workspaceId="w1"
          decision={undefined}
          highlighted={false}
          isEditing={true}
          onStartEdit={vi.fn()}
          onEndEdit={vi.fn()}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
          onToggleReaction={vi.fn()}
          onToggleDecision={vi.fn()}
          onReply={onReply}
          onScrollToComment={vi.fn()}
        />
      )
      const row = container.querySelector('[data-comment-id="c1"]') as HTMLElement

      fireEvent.touchStart(row, touches(200, 100))
      fireEvent.touchMove(row, touches(110, 100))
      fireEvent.touchEnd(row)

      expect(onReply).not.toHaveBeenCalled()
    })
  })

  it("renders the decision marker and toggles by the comment's global_id", () => {
    // Undecided: a quiet "Decide" affordance; clicking toggles by global_id.
    const { onToggleDecision, unmount } = renderItem(comment(), "author")
    expect(screen.queryByText("Decision")).toBeNull()
    fireEvent.click(screen.getByLabelText("Decide"))
    expect(onToggleDecision).toHaveBeenCalledWith("gid://convictional/EmailThreadComment/c1")
    unmount()

    // Decided: the green pill with the "Decision" label.
    const decision: Decision = {
      id: "d1",
      comment_gid: "gid://convictional/EmailThreadComment/c1",
      comment_preview: "Hello world",
      decided_by: null,
      decided_at: "2026-01-02T00:00:00Z",
    }
    renderItem(comment(), "author", decision)
    expect(screen.getByText("Decision")).toBeTruthy()
  })
})
