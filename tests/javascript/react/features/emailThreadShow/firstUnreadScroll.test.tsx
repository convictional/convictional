import { afterEach, describe, expect, it, vi } from "vitest"

import { cleanup, render } from "../../shared/testUtils"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))
// No channel-backed live updates here; resolve the hook to the null it would
// return anyway, without the "not available at mount" warning.
vi.mock("~/react/shared/hooks/useChannelsClient", () => ({ useChannelsClient: () => null }))
vi.mock("~/react/ui/Dropdown", () => ({ Dropdown: () => null }))

import { Timeline } from "~/react/features/emailThreadShow/components/Timeline"
import { collapsedMessageIdsFor, firstUnreadMessageId, lastMessageId } from "~/react/features/emailThreadShow/readState"
import { useInitialThreadScroll } from "~/react/features/emailThreadShow/hooks/useInitialThreadScroll"
import type { TimelineItem } from "~/react/shared/types"

const message = (id: string, receivedAt: string): TimelineItem => ({
  type: "message",
  item_id: id,
  created_at: receivedAt,
  event: null,
  message: {
    id,
    message_type: "received",
    subject: null,
    raw_sender: null,
    sender_name: id,
    sender_email: `${id}@example.com`,
    to: [],
    cc: [],
    bcc: [],
    preview: `preview ${id}`,
    received_at: receivedAt,
    sent_at: null,
    created_at: receivedAt,
    external_thread_id: null,
    message_id: null,
    content_url: `/content/${id}`,
    reply_url: "",
    forward_url: "",
    view_original_url: "",
  },
})

const TIMELINE = [
  message("a", "2025-01-01T00:00:00Z"),
  message("b", "2025-01-02T00:00:00Z"),
  message("c", "2025-01-03T00:00:00Z"),
]

// Drives the real derive -> mount -> callback-ref path (the path the old
// timer-based hook never exercised): the parent's target derivation picks the
// target (first unread, else the newest message), Timeline mounts it, and
// useInitialThreadScroll's callback ref — the same wiring EmailThreadShow uses —
// scrolls the instant that node commits.
function Harness({
  timeline,
  readAt,
  isUnread,
  scrollKey,
}: {
  timeline: TimelineItem[]
  readAt: string | null
  isUnread: boolean
  scrollKey: string | null
}) {
  const scrollTargetId = firstUnreadMessageId(timeline, readAt, isUnread) ?? lastMessageId(timeline)
  const collapsedMessageIds = collapsedMessageIdsFor(timeline, readAt, isUnread)
  const registerScrollTarget = useInitialThreadScroll(scrollKey)
  return (
    <Timeline
      items={timeline}
      comments={[]}
      collapsedMessageIds={collapsedMessageIds}
      canReply={false}
      isSuperuser={false}
      currentUserEmail={null}
      currentUserId={null}
      workspaceId="w1"
      decisionsByGid={new Map()}
      highlightedCommentId={null}
      scrollTargetId={scrollTargetId}
      scrollTargetRef={registerScrollTarget}
      onReply={vi.fn()}
      onReplyAll={vi.fn()}
      onForward={vi.fn()}
      onEditComment={vi.fn()}
      onDeleteComment={vi.fn()}
      onToggleReaction={vi.fn()}
      onToggleDecision={vi.fn()}
    />
  )
}

function spyScrollIntoView(): Element[] {
  const scrolled: Element[] = []
  vi.spyOn(Element.prototype, "scrollIntoView").mockImplementation(function (this: Element) {
    scrolled.push(this)
  })
  return scrolled
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.location.hash = ""
})

describe("first-unread initial scroll", () => {
  it("scrolls once to a mid-thread first-unread message", () => {
    const scrolled = spyScrollIntoView()

    // Read up to mid-thread: "b" is the oldest unread message.
    render(<Harness timeline={TIMELINE} readAt="2025-01-01T12:00:00Z" isUnread={true} scrollKey="t:read" />)

    expect(scrolled).toHaveLength(1)
    expect(scrolled[0].getAttribute("data-message-id")).toBe("b")
  })

  it("scrolls once to the last message when it is the sole unread one (the racy case)", () => {
    const scrolled = spyScrollIntoView()

    // Only the final message arrived after read_at — the case that landed at the
    // document bottom or top nondeterministically with the old timer + null fallback.
    render(<Harness timeline={TIMELINE} readAt="2025-01-02T12:00:00Z" isUnread={true} scrollKey="t:read" />)

    expect(scrolled).toHaveLength(1)
    expect(scrolled[0].getAttribute("data-message-id")).toBe("c")
  })

  it("scrolls once to the newest message when the thread is fully read", () => {
    const scrolled = spyScrollIntoView()

    // Nothing unread: the unified model top-aligns the last message instead of
    // jumping to the document bottom.
    render(<Harness timeline={TIMELINE} readAt="2025-01-04T00:00:00Z" isUnread={false} scrollKey="t:read" />)

    expect(scrolled).toHaveLength(1)
    expect(scrolled[0].getAttribute("data-message-id")).toBe("c")
  })

  it("does not scroll to a message when a #comment- deep link is present", () => {
    const scrolled = spyScrollIntoView()
    window.location.hash = "#comment-xyz"

    render(<Harness timeline={TIMELINE} readAt="2025-01-02T12:00:00Z" isUnread={true} scrollKey="t:read" />)

    expect(scrolled).toHaveLength(0)
  })

  it("does not re-scroll when a live message arrives on the same scrollKey", () => {
    const scrolled = spyScrollIntoView()

    const { rerender } = render(
      <Harness timeline={TIMELINE} readAt="2025-01-02T12:00:00Z" isUnread={true} scrollKey="t:read" />
    )
    expect(scrolled).toHaveLength(1)

    // A realtime arrival appends a newer message but the scrollKey is unchanged —
    // the once-per-key guard keeps this strictly an initial scroll.
    rerender(
      <Harness
        timeline={[...TIMELINE, message("d", "2025-01-04T00:00:00Z")]}
        readAt="2025-01-02T12:00:00Z"
        isUnread={true}
        scrollKey="t:read"
      />
    )
    expect(scrolled).toHaveLength(1)
  })
})
