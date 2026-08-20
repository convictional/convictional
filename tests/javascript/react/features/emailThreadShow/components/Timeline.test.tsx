import { cleanup, render } from "../../../shared/testUtils"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))
// No channel-backed live updates here; resolve the hook to the null it would
// return anyway, without the "not available at mount" warning.
vi.mock("~/react/shared/hooks/useChannelsClient", () => ({ useChannelsClient: () => null }))
vi.mock("~/react/ui/Dropdown", () => ({
  Dropdown: () => null,
}))
// Stub the heavy ProseMirror-backed editor so the edit-mode pass-through test
// stays focused on Timeline routing isEditing to the right comment.
vi.mock("~/react/features/emailThreadShow/components/EmailThreadCommentEditor", () => ({
  EmailThreadCommentEditor: () => <div data-testid="comment-editor" />,
}))

import { Timeline } from "~/react/features/emailThreadShow/components/Timeline"
import type { EmailMessage as EmailMessageType, TimelineItem, EmailThreadComment } from "~/react/shared/types"

const commentHandlers = {
  comments: [] as EmailThreadComment[],
  currentUserId: null,
  workspaceId: "w1",
  decisionsByGid: new Map(),
  highlightedCommentId: null,
  editingCommentId: null,
  onStartEditComment: vi.fn(),
  onEndEditComment: vi.fn(),
  onEditComment: vi.fn(),
  onDeleteComment: vi.fn(),
  onToggleReaction: vi.fn(),
  onToggleDecision: vi.fn(),
  onReplyToComment: vi.fn(),
  onScrollToComment: vi.fn(),
}

const fakeMessage = (id: string): EmailMessageType => ({
  id,
  message_type: "received",
  subject: null,
  sender_name: `Sender ${id}`,
  sender_email: `${id}@example.com`,
  to: [],
  cc: [],
  bcc: [],
  preview: `Preview ${id}`,
  content_html: `<p>body ${id}</p>`,
  body_plain: null,
  received_at: null,
  sent_at: null,
  created_at: "2026-01-01T00:00:00Z",
  content_url: `/content/${id}`,
  reply_url: "/r",
  forward_url: "/f",
  view_original_url: "/o",
  attachments: [],
})

const items: TimelineItem[] = [
  { type: "message", item_id: "m1", created_at: "2026-01-01", message: fakeMessage("m1"), event: null },
  {
    type: "event",
    item_id: "e1",
    created_at: "2026-01-02",
    message: null,
    event: {
      id: "e1",
      action: "assigned",
      created_at: "2026-01-02",
      creator: { id: "u1", display_name: "Alice", picture: null },
      details: { type: "assigned", subject_label: "Bob" },
    },
  },
  { type: "message", item_id: "m2", created_at: "2026-01-03", message: fakeMessage("m2"), event: null },
]

afterEach(() => cleanup())

describe("Timeline", () => {
  it("renders messages and activity events in order with stable keys", () => {
    const { container } = render(
      <Timeline
        items={items}
        {...commentHandlers}
        collapsedMessageIds={new Set()}
        canReply={true}
        isSuperuser={false}
        currentUserEmail={null}
        onReply={vi.fn()}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />
    )
    const messageNodes = container.querySelectorAll("[data-message-id]")
    expect(messageNodes).toHaveLength(2)
    expect(messageNodes[0].getAttribute("data-message-id")).toBe("m1")
    expect(messageNodes[1].getAttribute("data-message-id")).toBe("m2")
    expect(container.querySelector("[data-event-id='e1']")).toBeTruthy()
    expect(container.innerHTML).toContain("Alice assigned to Bob")
  })

  it("flags only the most recent message as the last message", () => {
    const { container } = render(
      <Timeline
        items={items}
        {...commentHandlers}
        collapsedMessageIds={new Set()}
        canReply={true}
        isSuperuser={false}
        currentUserEmail={null}
        onReply={vi.fn()}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />
    )
    // The primary action row (data-hotkey="r") only renders for the last
    // message — exactly one should be present.
    expect(container.querySelectorAll('[data-hotkey="r"]')).toHaveLength(1)
  })

  it("wires scrollTargetRef onto the matching message node only", () => {
    const scrollTargetRef = vi.fn()
    render(
      <Timeline
        items={items}
        {...commentHandlers}
        collapsedMessageIds={new Set()}
        canReply={true}
        isSuperuser={false}
        currentUserEmail={null}
        scrollTargetId="m2"
        scrollTargetRef={scrollTargetRef}
        onReply={vi.fn()}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />
    )
    // The callback ref fires only for the target message (m2), receiving its DOM node.
    const node = scrollTargetRef.mock.calls.at(-1)?.[0] as HTMLElement | null
    expect(node).toBeTruthy()
    expect(node?.getAttribute("data-message-id")).toBe("m2")
  })

  it("does not call scrollTargetRef when no message matches scrollTargetId", () => {
    const scrollTargetRef = vi.fn()
    render(
      <Timeline
        items={items}
        {...commentHandlers}
        collapsedMessageIds={new Set()}
        canReply={true}
        isSuperuser={false}
        currentUserEmail={null}
        scrollTargetId={null}
        scrollTargetRef={scrollTargetRef}
        onReply={vi.fn()}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />
    )
    expect(scrollTargetRef).not.toHaveBeenCalledWith(expect.any(HTMLElement))
  })

  it("merges comments into the timeline by created_at", () => {
    const comment: EmailThreadComment = {
      id: "wc1",
      global_id: "gid://convictional/EmailThreadComment/wc1",
      content: "An internal note",
      user: { id: "u9", display_name: "Dana", picture: null },
      created_at: "2026-01-02T12:00:00Z",
      updated_at: "2026-01-02T12:00:00Z",
      reactions: {},
      link_preview: null,
      attachments: [],
      reply_to: null,
    }
    const { container } = render(
      <Timeline
        items={items}
        {...commentHandlers}
        comments={[comment]}
        collapsedMessageIds={new Set()}
        canReply={true}
        isSuperuser={false}
        currentUserEmail={null}
        onReply={vi.fn()}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />
    )
    expect(container.querySelector("[data-comment-id='wc1']")).toBeTruthy()
    expect(container.innerHTML).toContain("An internal note")

    // The comment (2026-01-02T12:00) splices between the e1 event (2026-01-02)
    // and the m2 message (2026-01-03) by created_at.
    const order = Array.from(container.querySelectorAll("[data-message-id], [data-event-id], [data-comment-id]")).map(
      node =>
        node.getAttribute("data-message-id") ??
        node.getAttribute("data-event-id") ??
        node.getAttribute("data-comment-id")
    )
    expect(order).toEqual(["m1", "e1", "wc1", "m2"])
  })

  it("breaks same-author grouping for a reply so its quote and header read clearly", () => {
    const base = (id: string, replyTo: EmailThreadComment["reply_to"]): EmailThreadComment => ({
      id,
      global_id: `gid://convictional/EmailThreadComment/${id}`,
      content: `note ${id}`,
      user: { id: "u9", display_name: "Dana", picture: null },
      // Within the group window and same author, so wc2 would normally group onto wc1.
      created_at: id === "wc1" ? "2026-01-04T12:00:00Z" : "2026-01-04T12:00:30Z",
      updated_at: "2026-01-04T12:00:00Z",
      reactions: {},
      link_preview: null,
      attachments: [],
      reply_to: replyTo,
    })
    const wrapperClass = (container: HTMLElement, id: string) =>
      container.querySelector(`[data-comment-id="${id}"]`)?.parentElement?.className ?? ""

    // Control: a plain follow-up groups (tight negative-margin wrapper).
    const control = render(
      <Timeline
        items={[]}
        {...commentHandlers}
        comments={[base("wc1", null), base("wc2", null)]}
        collapsedMessageIds={new Set()}
        canReply
        isSuperuser={false}
        currentUserEmail={null}
        onReply={vi.fn()}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />
    )
    expect(wrapperClass(control.container, "wc2")).toContain("-mt-3.5")
    cleanup()

    // A reply follow-up does not group.
    const reply = render(
      <Timeline
        items={[]}
        {...commentHandlers}
        comments={[
          base("wc1", null),
          base("wc2", { id: "wc1", user_name: "Dana", content_preview: "note wc1", is_deleted: false }),
        ]}
        collapsedMessageIds={new Set()}
        canReply
        isSuperuser={false}
        currentUserEmail={null}
        onReply={vi.fn()}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />
    )
    expect(wrapperClass(reply.container, "wc2")).not.toContain("-mt-3.5")
  })

  it("puts only the comment matching editingCommentId into edit mode", () => {
    const mkComment = (id: string): EmailThreadComment => ({
      id,
      global_id: `gid://convictional/EmailThreadComment/${id}`,
      content: `note ${id}`,
      user: { id: "u9", display_name: "Dana", picture: null },
      created_at: "2026-01-02T12:00:00Z",
      updated_at: "2026-01-02T12:00:00Z",
      reactions: {},
      link_preview: null,
      attachments: [],
      reply_to: null,
    })
    const { container } = render(
      <Timeline
        items={items}
        {...commentHandlers}
        comments={[mkComment("wc1"), mkComment("wc2")]}
        editingCommentId="wc2"
        collapsedMessageIds={new Set()}
        canReply={true}
        isSuperuser={false}
        currentUserEmail={null}
        onReply={vi.fn()}
        onReplyAll={vi.fn()}
        onForward={vi.fn()}
      />
    )
    // Exactly one comment is in edit mode, and it's wc2.
    const editors = container.querySelectorAll('[data-testid="comment-editor"]')
    expect(editors).toHaveLength(1)
    expect(container.querySelector('[data-comment-id="wc2"] [data-testid="comment-editor"]')).toBeTruthy()
  })
})
