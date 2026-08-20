import { act, renderHook } from "@testing-library/react"
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

const reconnectListeners = new Set<() => void>()
const fakeClient = {
  on: (event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners.add(cb)
  },
  off: (event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners.delete(cb)
  },
}

vi.mock("~/react/shared/hooks/useChannelsClient", () => ({
  useChannelsClient: () => fakeClient,
}))

import { useDraftBroadcast } from "~/react/composites/emailComposer/hooks/useDraftBroadcast"

interface EnvelopeStub {
  applyRemoteTo: ReturnType<typeof vi.fn>
  applyRemoteCc: ReturnType<typeof vi.fn>
  applyRemoteBcc: ReturnType<typeof vi.fn>
  applyRemoteSubject: ReturnType<typeof vi.fn>
}

function makeEnvelopeStub(dirtyFields: Set<string> = new Set()): EnvelopeStub {
  return {
    applyRemoteTo: vi.fn(() => !dirtyFields.has("to")),
    applyRemoteCc: vi.fn(() => !dirtyFields.has("cc")),
    applyRemoteBcc: vi.fn(() => !dirtyFields.has("bcc")),
    applyRemoteSubject: vi.fn(() => !dirtyFields.has("subject")),
  }
}

describe("useDraftBroadcast", () => {
  beforeEach(() => {
    registeredHandler = null
    reconnectListeners.clear()
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("DRAFT_UPDATED applies clean fields and skips dirty ones", () => {
    const envelope = makeEnvelopeStub(new Set(["subject"]))
    const onRemoved = vi.fn()

    renderHook(() =>
      useDraftBroadcast({
        threadId: "T",
        draftUrl: "/api/email_threads/T/draft",
        envelope: envelope as never,
        onRemoved,
      })
    )

    act(() => {
      registeredHandler?.(ChannelEventAction.DRAFT_UPDATED, {
        envelope: { to: ["x@example.com"], subject: "remote" },
      })
    })

    expect(envelope.applyRemoteTo).toHaveBeenCalledWith(["x@example.com"])
    expect(envelope.applyRemoteSubject).toHaveBeenCalledWith("remote")
    // The hook calls each apply method unconditionally and trusts its return
    // value — the stub returns false for the dirty `subject`.
    expect(envelope.applyRemoteSubject.mock.results[0]?.value).toBe(false)
  })

  it("ASSIGNMENT_CHANGED applies unconditionally via onAssignmentChanged", () => {
    const envelope = makeEnvelopeStub()
    const onAssignmentChanged = vi.fn()
    const onRemoved = vi.fn()

    renderHook(() =>
      useDraftBroadcast({
        threadId: "T",
        draftUrl: "/api/email_threads/T/draft",
        envelope: envelope as never,
        onRemoved,
        onAssignmentChanged,
      })
    )

    act(() => {
      registeredHandler?.(ChannelEventAction.ASSIGNMENT_CHANGED, {
        sendable_by: "Sendable by you (owner)",
        can_reply: true,
        cannot_send_reason: null,
      })
    })

    expect(onAssignmentChanged).toHaveBeenCalledWith({
      sendableBy: "Sendable by you (owner)",
      canReply: true,
      cannotSendReason: null,
    })
    expect(envelope.applyRemoteTo).not.toHaveBeenCalled()
    expect(envelope.applyRemoteSubject).not.toHaveBeenCalled()
  })

  it("DRAFT_REMOVED disconnects collaboration before invoking onRemoved", () => {
    const envelope = makeEnvelopeStub()
    const callOrder: string[] = []
    const disconnectCollaboration = vi.fn(() => callOrder.push("disconnect"))
    const onRemoved = vi.fn(() => callOrder.push("onRemoved"))

    renderHook(() =>
      useDraftBroadcast({
        threadId: "T",
        draftUrl: "/api/email_threads/T/draft",
        envelope: envelope as never,
        onRemoved,
        disconnectCollaboration,
      })
    )

    act(() => {
      registeredHandler?.(ChannelEventAction.DRAFT_REMOVED, { user_id: "other" })
    })

    expect(disconnectCollaboration).toHaveBeenCalled()
    expect(onRemoved).toHaveBeenCalled()
    expect(callOrder).toEqual(["disconnect", "onRemoved"])
  })

  it("DRAFT_STARTED is ignored by the running composer", () => {
    const envelope = makeEnvelopeStub()
    const onRemoved = vi.fn()
    const onAssignmentChanged = vi.fn()

    renderHook(() =>
      useDraftBroadcast({
        threadId: "T",
        draftUrl: "/api/email_threads/T/draft",
        envelope: envelope as never,
        onRemoved,
        onAssignmentChanged,
      })
    )

    act(() => {
      registeredHandler?.(ChannelEventAction.DRAFT_STARTED, { user_id: "other" })
    })

    expect(envelope.applyRemoteTo).not.toHaveBeenCalled()
    expect(envelope.applyRemoteSubject).not.toHaveBeenCalled()
    expect(onRemoved).not.toHaveBeenCalled()
    expect(onAssignmentChanged).not.toHaveBeenCalled()
  })

  it("reconnect refetches the draft and applies the response with dirty-flag gating", async () => {
    const envelope = makeEnvelopeStub(new Set(["subject"]))
    const onAssignmentChanged = vi.fn()
    apiFetchMock.mockResolvedValue({
      to: ["x@example.com"],
      cc: [],
      bcc: [],
      subject: "remote",
      in_reply_to_id: null,
      sendable_by: "Sendable by you",
      can_reply: true,
      cannot_send_reason: null,
    })

    renderHook(() =>
      useDraftBroadcast({
        threadId: "T",
        draftUrl: "/api/email_threads/T/draft",
        envelope: envelope as never,
        onRemoved: vi.fn(),
        onAssignmentChanged,
      })
    )

    expect(reconnectListeners.size).toBe(1)

    await act(async () => {
      for (const listener of reconnectListeners) {
        await listener()
      }
    })

    expect(apiFetchMock).toHaveBeenCalledWith("/api/email_threads/T/draft", undefined)
    expect(envelope.applyRemoteTo).toHaveBeenCalledWith(["x@example.com"])
    expect(envelope.applyRemoteSubject).toHaveBeenCalledWith("remote")
    expect(onAssignmentChanged).toHaveBeenCalledWith({
      sendableBy: "Sendable by you",
      canReply: true,
      cannotSendReason: null,
    })
  })
})
