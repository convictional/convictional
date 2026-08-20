import { describe, expect, it } from "vitest"

import { renderHook } from "../../../shared/testUtils"

import { useInitialScrollTarget } from "~/react/features/emailThreadShow/hooks/useInitialScrollTarget"
import type { EmailThreadShowResponse, TimelineItem } from "~/react/shared/types"

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

function response({
  threadId = "t1",
  readAt,
  isUnread,
  timeline = TIMELINE,
}: {
  threadId?: string
  readAt: string | null
  isUnread: boolean
  timeline?: TimelineItem[]
}): EmailThreadShowResponse {
  return {
    thread: {
      id: threadId,
      title: "Long newsletter",
      workspace_id: "w1",
      creator: { id: "u1", display_name: "Sender" },
      can_reply: true,
      is_shared: false,
      own_thread_id: null,
    },
    mailbox_entry: {
      id: "m1",
      is_unread: isUnread,
      is_archived: false,
      is_snoozed: false,
      snoozed_until: null,
      is_ai_excluded: false,
      is_shared: false,
      read_at: readAt,
    },
    back: { url: "/mailbox", label: "Back" },
    timeline,
    comments: [],
    draft: null,
    last_event_id: null,
  }
}

describe("useInitialScrollTarget", () => {
  it("returns nulls until the first load lands", () => {
    const { result } = renderHook(({ data }) => useInitialScrollTarget("t1", data, null), {
      initialProps: { data: null as EmailThreadShowResponse | null },
    })
    expect(result.current).toEqual({
      scrollKey: null,
      messageScrollTargetId: null,
      commentScrollTargetId: null,
      readCursor: null,
      hasCollapsedGroup: false,
    })
  })

  it("targets the first unread message on load", () => {
    // read_at null + unread: nothing has been read, so the earliest message is the target.
    const { result } = renderHook(() => useInitialScrollTarget("t1", response({ readAt: null, isUnread: true }), null))
    expect(result.current.scrollKey).toBe("t1:unread")
    expect(result.current.messageScrollTargetId).toBe("a")
  })

  it("freezes the scroll key and target across a reconnect refetch that marks the thread read (#8838)", () => {
    // Open unread → target the top of the thread. A reconnect refetch then rehydrates `data`
    // with the now-read mailbox_entry (opening the thread marked it read). The frozen snapshot
    // must keep the key and target put, so the initial scroll never re-fires and yanks the
    // reader to the top of the email.
    const { result, rerender } = renderHook(({ data }) => useInitialScrollTarget("t1", data, null), {
      initialProps: { data: response({ readAt: null, isUnread: true }) },
    })

    const initial = result.current
    expect(initial.scrollKey).toBe("t1:unread")
    expect(initial.messageScrollTargetId).toBe("a")

    // Reconnect refetch: same thread, now fully read (read_at after the newest message).
    rerender({ data: response({ readAt: "2025-01-04T00:00:00Z", isUnread: false }) })

    expect(result.current.scrollKey).toBe("t1:unread")
    expect(result.current.messageScrollTargetId).toBe("a")
    expect(result.current.readCursor).toEqual({ readAt: null, isUnread: true })
  })

  it("does not move the target when a live message arrives via refetch", () => {
    const { result, rerender } = renderHook(({ data }) => useInitialScrollTarget("t1", data, null), {
      initialProps: { data: response({ readAt: "2025-01-04T00:00:00Z", isUnread: false }) },
    })
    // Fully read → newest message.
    expect(result.current.messageScrollTargetId).toBe("c")

    // A newer message arrives on refetch; the frozen snapshot ignores it.
    rerender({
      data: response({
        readAt: "2025-01-04T00:00:00Z",
        isUnread: false,
        timeline: [...TIMELINE, message("d", "2025-01-05T00:00:00Z")],
      }),
    })
    expect(result.current.messageScrollTargetId).toBe("c")
  })

  it("freezes hasCollapsedGroup so a later refetch that shortens the read run can't un-suppress the scroll", () => {
    // A long fully-read thread: the boundary is the always-expanded newest message, so the
    // read run before it (5 messages) is long enough to compact — hasCollapsedGroup is true and
    // the initial scroll stays suppressed at the top. A reconnect refetch that drops messages
    // out of the run (e.g. a deletion) must NOT flip the frozen decision, or the once-suppressed
    // scroll would fire late and yank the reader down mid-read.
    const longThread = [
      message("a", "2025-01-01T00:00:00Z"),
      message("b", "2025-01-02T00:00:00Z"),
      message("c", "2025-01-03T00:00:00Z"),
      message("d", "2025-01-04T00:00:00Z"),
      message("e", "2025-01-05T00:00:00Z"),
      message("f", "2025-01-06T00:00:00Z"),
    ]
    const { result, rerender } = renderHook(({ data }) => useInitialScrollTarget("t1", data, null), {
      initialProps: {
        data: response({ readAt: "2025-01-07T00:00:00Z", isUnread: false, timeline: longThread }),
      },
    })
    expect(result.current.hasCollapsedGroup).toBe(true)

    // Refetch with a run too short to compact on its own; the frozen decision holds.
    rerender({ data: response({ readAt: "2025-01-07T00:00:00Z", isUnread: false, timeline: TIMELINE }) })
    expect(result.current.hasCollapsedGroup).toBe(true)
  })

  it("re-latches when the thread id changes (a remount in practice)", () => {
    const { result, rerender } = renderHook(({ threadId, data }) => useInitialScrollTarget(threadId, data, null), {
      initialProps: { threadId: "t1", data: response({ readAt: null, isUnread: true }) },
    })
    expect(result.current.scrollKey).toBe("t1:unread")

    rerender({ threadId: "t2", data: response({ threadId: "t2", readAt: "2025-01-04T00:00:00Z", isUnread: false }) })
    expect(result.current.scrollKey).toBe("t2:2025-01-04T00:00:00Z")
    expect(result.current.messageScrollTargetId).toBe("c")
  })
})
