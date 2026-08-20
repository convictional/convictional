import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ChannelEventAction } from "~/types/channels"

const apiFetchMock = vi.fn()
vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: (url: string, options?: RequestInit) => apiFetchMock(url, options),
}))

let registeredHandler: ((action: string, data: Record<string, unknown>) => void) | null = null
vi.mock("~/react/shared/hooks/useChannel", () => ({
  useChannel: (
    _target: { stream: string; params: Record<string, unknown> } | null,
    _resource: string,
    onMessage: (action: string, data: Record<string, unknown>) => void
  ) => {
    registeredHandler = onMessage
  },
}))

import { useReplyComposer } from "~/react/features/emailThreadShow/hooks/useReplyComposer"

function composerWireFixture(threadId = "T") {
  return {
    thread_id: threadId,
    draft_message_id: "draft-1",
    current_user: { id: "u1", display_name: "Alice", picture: null },
    upload_url: "/upload",
    attachments_base_url: "/attachments",
    patch_url: "/patch",
    send_url: "/send",
    schedule_url: "/schedule",
    unschedule_url: "/unschedule",
    delete_url: "/delete",
    draft_url: "/draft",
    initial_envelope: {
      to: ["x@example.com"],
      cc: [],
      bcc: [],
      subject: "Hello",
      in_reply_to_id: null,
      attachments: [],
      sendable_by: "me",
      can_reply: true,
      cannot_send_reason: null,
      is_scheduled: false,
      scheduled_for: null,
    },
    is_shared_draft: false,
    mailbox_index_url: "/mailbox",
    default_snooze_times: [],
  }
}

beforeEach(() => {
  registeredHandler = null
  apiFetchMock.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("useReplyComposer", () => {
  it("DRAFT_STARTED fetches the composer wire and sets props", async () => {
    apiFetchMock.mockResolvedValueOnce(composerWireFixture())
    const { result } = renderHook(() =>
      useReplyComposer({ threadId: "T", initialDraft: null, currentUserId: "u1" })
    )

    expect(result.current.composerProps).toBeNull()

    await act(async () => {
      registeredHandler?.(ChannelEventAction.DRAFT_STARTED, { thread_id: "T", user_id: "other" })
    })

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith("/api/email_threads/T/composer", expect.objectContaining({ signal: expect.any(AbortSignal) }))
      expect(result.current.composerProps).not.toBeNull()
      expect(result.current.composerProps?.draftMessageId).toBe("draft-1")
    })
  })

  it("concurrent fetches: only the latest resolution updates state", async () => {
    let resolveFirst: ((value: unknown) => void) | null = null
    let resolveSecond: ((value: unknown) => void) | null = null
    apiFetchMock.mockImplementationOnce(() => new Promise(r => { resolveFirst = r }))
    apiFetchMock.mockImplementationOnce(() => new Promise(r => { resolveSecond = r }))

    const { result } = renderHook(() =>
      useReplyComposer({ threadId: "T", initialDraft: null, currentUserId: "u1" })
    )

    act(() => {
      result.current.mountAfterAction()
    })
    act(() => {
      registeredHandler?.(ChannelEventAction.DRAFT_STARTED, { thread_id: "T", user_id: "other" })
    })

    // Resolve the second (newest) call first.
    await act(async () => {
      resolveSecond?.(composerWireFixture("T"))
    })
    // Then resolve the first (now-aborted) call with a value that would
    // overwrite the second — the abort guard must keep state from the newest.
    await act(async () => {
      resolveFirst?.({ ...composerWireFixture("T"), draft_message_id: "stale" })
    })

    await waitFor(() => {
      expect(result.current.composerProps?.draftMessageId).toBe("draft-1")
    })
  })

  it("DRAFT_STARTED from the same user is skipped", async () => {
    apiFetchMock.mockResolvedValue(composerWireFixture())
    renderHook(() =>
      useReplyComposer({ threadId: "T", initialDraft: null, currentUserId: "u1" })
    )
    act(() => {
      registeredHandler?.(ChannelEventAction.DRAFT_STARTED, { thread_id: "T", user_id: "u1" })
    })
    // Microtask drain
    await Promise.resolve()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it("DRAFT_REMOVED from the same user is skipped", async () => {
    apiFetchMock.mockResolvedValue(composerWireFixture())
    const { result } = renderHook(() =>
      useReplyComposer({
        threadId: "T",
        initialDraft: { message_id: "draft-1", composer_url: "/api/email_threads/T/composer" },
        currentUserId: "u1",
      })
    )
    await waitFor(() => expect(result.current.composerProps).not.toBeNull())

    act(() => {
      registeredHandler?.(ChannelEventAction.DRAFT_REMOVED, { user_id: "u1" })
    })
    expect(result.current.composerProps).not.toBeNull()
  })

  it("DRAFT_REMOVED clears composer props", async () => {
    apiFetchMock.mockResolvedValueOnce(composerWireFixture())
    const { result } = renderHook(() =>
      useReplyComposer({
        threadId: "T",
        initialDraft: { message_id: "draft-1", composer_url: "/api/email_threads/T/composer" },
        currentUserId: "u1",
      })
    )
    await waitFor(() => expect(result.current.composerProps).not.toBeNull())

    act(() => {
      registeredHandler?.(ChannelEventAction.DRAFT_REMOVED, { user_id: "other" })
    })
    expect(result.current.composerProps).toBeNull()
  })

  it("mountAfterAction triggers a refetch with focusBody=true", async () => {
    apiFetchMock.mockResolvedValue(composerWireFixture())
    const { result } = renderHook(() =>
      useReplyComposer({ threadId: "T", initialDraft: null, currentUserId: "u1" })
    )

    act(() => {
      result.current.mountAfterAction()
    })
    await waitFor(() => {
      expect(result.current.composerProps?.focusBody).toBe(true)
    })
  })

  it("bootstrap from initialDraft sets focusBody=false", async () => {
    apiFetchMock.mockResolvedValueOnce(composerWireFixture())
    const { result } = renderHook(() =>
      useReplyComposer({
        threadId: "T",
        initialDraft: { message_id: "draft-1", composer_url: "/api/email_threads/T/composer" },
        currentUserId: "u1",
      })
    )

    await waitFor(() => expect(result.current.composerProps).not.toBeNull())
    expect(result.current.composerProps?.focusBody).toBe(false)
  })

  it("DRAFT_STARTED from another user sets focusBody=false", async () => {
    apiFetchMock.mockResolvedValueOnce(composerWireFixture())
    const { result } = renderHook(() =>
      useReplyComposer({ threadId: "T", initialDraft: null, currentUserId: "u1" })
    )

    await act(async () => {
      registeredHandler?.(ChannelEventAction.DRAFT_STARTED, { thread_id: "T", user_id: "other" })
    })

    await waitFor(() => expect(result.current.composerProps).not.toBeNull())
    expect(result.current.composerProps?.focusBody).toBe(false)
  })
})
