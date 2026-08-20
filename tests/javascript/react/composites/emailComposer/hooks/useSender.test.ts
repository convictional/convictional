import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { useSender } from "~/react/composites/emailComposer/hooks/useSender"

const apiFetchMock = vi.fn()

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: (url: string, options?: RequestInit) => apiFetchMock(url, options),
}))

vi.mock("~/react/composites/confirmationDialog/confirm", () => ({
  confirm: vi.fn(async () => true),
}))

const confirmMock = vi.mocked(confirm)

// boostedNavigate performs a full-document navigation (window.location.href)
// when htmx is absent, as it is in this unit test.
const hrefMock = vi.fn()
beforeEach(() => {
  apiFetchMock.mockReset()
  confirmMock.mockReset()
  confirmMock.mockResolvedValue(true)
  hrefMock.mockReset()
  Object.defineProperty(window, "location", {
    value: Object.defineProperty({}, "href", { set: hrefMock, configurable: true }) as unknown as Location,
    writable: true,
    configurable: true,
  })
})

const baseEnvelope = (
  overrides: Partial<{
    to: string[]
    cc: string[]
    bcc: string[]
    subject: string
  }> = {}
) => ({
  to: ["alice@example.com"],
  cc: [],
  bcc: [],
  subject: "Hello",
  resetDirty: vi.fn(),
  ...overrides,
})

const SEND_URL = "/api/email_threads/T/draft/send"
const SCHEDULE_URL = "/api/email_threads/T/draft/schedule"
const MAILBOX_INDEX_URL = "/inbox"

describe("useSender", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("schedule POSTs scheduled_for and notifies onScheduled without navigating", async () => {
    apiFetchMock.mockResolvedValue({ scheduled_for: "2030-01-01T09:00:00Z", body_html: "<p>Body markdown</p>" })
    const onScheduled = vi.fn()
    const envelope = baseEnvelope()

    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        scheduleUrl: SCHEDULE_URL,
        canReply: true,
        cannotSendReason: null,
        envelope,
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
        onScheduled,
      })
    )

    await act(async () => {
      await result.current.schedule("2030-01-01T09:00:00Z", "Body markdown")
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    const [url, options] = apiFetchMock.mock.calls[0]
    expect(url).toBe(SCHEDULE_URL)
    expect(options.method).toBe("POST")
    expect(JSON.parse(options.body)).toEqual({
      subject: "Hello",
      to: ["alice@example.com"],
      cc: [],
      bcc: [],
      message_body: "Body markdown",
      should_archive: false,
      scheduled_for: "2030-01-01T09:00:00Z",
    })
    // A scheduled draft stays put — the server's authoritative time flows back
    // via onScheduled and there is no navigation.
    expect(onScheduled).toHaveBeenCalledWith("2030-01-01T09:00:00Z", "<p>Body markdown</p>")
    expect(envelope.resetDirty).toHaveBeenCalled()
    expect(hrefMock).not.toHaveBeenCalled()
  })

  it("derives canSend / cannotSendReason from envelope state", () => {
    const { result, rerender } = renderHook(
      ({ envelope, canReply, cannotSendReason }) =>
        useSender({
          sendUrl: SEND_URL,
          canReply,
          cannotSendReason,
          envelope,
          hasAttachments: false,
          mailboxIndexUrl: MAILBOX_INDEX_URL,
        }),
      {
        initialProps: {
          envelope: baseEnvelope(),
          canReply: true,
          cannotSendReason: null as string | null,
        },
      }
    )

    expect(result.current.canSend).toBe(true)

    rerender({
      envelope: baseEnvelope({ subject: "" }),
      canReply: true,
      cannotSendReason: null,
    })
    expect(result.current.canSend).toBe(true)

    rerender({
      envelope: baseEnvelope({ to: [] }),
      canReply: true,
      cannotSendReason: null,
    })
    expect(result.current.canSend).toBe(false)
    expect(result.current.cannotSendReason).toBe("To is required")

    rerender({
      envelope: baseEnvelope({ to: ["not-an-email"] }),
      canReply: true,
      cannotSendReason: null,
    })
    expect(result.current.canSend).toBe(false)
    expect(result.current.cannotSendReason).toContain("invalid")

    rerender({
      envelope: baseEnvelope(),
      canReply: false,
      cannotSendReason: "Only the owner can send",
    })
    expect(result.current.canSend).toBe(false)
    expect(result.current.cannotSendReason).toBe("Only the owner can send")
  })

  it("send POSTs the envelope + body markdown then navigates to the mailbox index by default", async () => {
    apiFetchMock.mockResolvedValue(undefined)

    const envelope = baseEnvelope()
    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope,
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
      })
    )

    await act(async () => {
      await result.current.send({ archive: true }, "Body markdown")
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    const [url, options] = apiFetchMock.mock.calls[0]
    expect(url).toBe(SEND_URL)
    expect(options.method).toBe("POST")
    const body = JSON.parse(options.body)
    expect(body).toEqual({
      subject: "Hello",
      to: ["alice@example.com"],
      cc: [],
      bcc: [],
      message_body: "Body markdown",
      should_archive: true,
      should_snooze: false,
      snoozed_until: null,
    })
    expect(envelope.resetDirty).toHaveBeenCalled()
    // Without a resolveSendDestination (e.g. a surface with no mailbox navigation),
    // the send falls back to the mailbox index it was opened from.
    expect(hrefMock).toHaveBeenCalledWith(MAILBOX_INDEX_URL)
  })

  it("advances to the next entry resolved by resolveSendDestination", async () => {
    apiFetchMock.mockResolvedValue(undefined)
    const resolveSendDestination = vi.fn().mockResolvedValue("/email_threads/next?return_to=%2F")

    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope: baseEnvelope(),
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
        resolveSendDestination,
      })
    )

    await act(async () => {
      await result.current.send({ snooze: true, snoozedUntil: "2030-01-01T09:00:00Z" }, "Body markdown")
    })

    // The resolver receives the send options so the caller can drop a snoozed entry
    // from its list cache before we advance.
    expect(resolveSendDestination).toHaveBeenCalledWith({
      snooze: true,
      snoozedUntil: "2030-01-01T09:00:00Z",
    })
    expect(hrefMock).toHaveBeenCalledWith("/email_threads/next?return_to=%2F")
  })

  it("falls back to the mailbox index when resolveSendDestination yields no next entry", async () => {
    apiFetchMock.mockResolvedValue(undefined)
    const resolveSendDestination = vi.fn().mockResolvedValue(null)

    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope: baseEnvelope(),
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
        resolveSendDestination,
      })
    )

    await act(async () => {
      await result.current.send({}, "Body markdown")
    })

    expect(resolveSendDestination).toHaveBeenCalledWith({})
    expect(hrefMock).toHaveBeenCalledWith(MAILBOX_INDEX_URL)
  })

  it("still navigates on a successful send when resolveSendDestination throws", async () => {
    apiFetchMock.mockResolvedValue(undefined)
    const resolveSendDestination = vi.fn().mockRejectedValue(new Error("boom"))

    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope: baseEnvelope(),
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
        resolveSendDestination,
      })
    )

    await act(async () => {
      await result.current.send({}, "Body markdown")
    })

    // A failed next-entry resolution must not strand the user on the sent draft.
    expect(hrefMock).toHaveBeenCalledWith(MAILBOX_INDEX_URL)
  })

  it("clears sending state on send failure", async () => {
    apiFetchMock.mockRejectedValue(new Error("boom"))

    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope: baseEnvelope(),
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
      })
    )

    await act(async () => {
      await result.current.send({}, "Body")
    })

    expect(result.current.sending).toBe(false)
    expect(hrefMock).not.toHaveBeenCalled()
  })

  it("does not clear dirty state when send fails", async () => {
    apiFetchMock.mockRejectedValue(new Error("boom"))

    const envelope = baseEnvelope()
    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope,
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
      })
    )

    await act(async () => {
      await result.current.send({}, "Body")
    })

    expect(envelope.resetDirty).not.toHaveBeenCalled()
  })

  it("guards against synchronous double-send", async () => {
    let resolveFetch: (value: unknown) => void = () => {}
    apiFetchMock.mockImplementation(
      () =>
        new Promise(resolve => {
          resolveFetch = resolve
        })
    )

    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope: baseEnvelope(),
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
      })
    )

    await act(async () => {
      void result.current.send({}, "Body")
      void result.current.send({}, "Body")
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveFetch(undefined)
    })
  })

  it("confirms before sending when subject and body are both empty", async () => {
    apiFetchMock.mockResolvedValue(undefined)

    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope: baseEnvelope({ subject: "" }),
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
      })
    )

    await act(async () => {
      await result.current.send({}, "")
    })

    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it("aborts the send when the empty-email confirmation is cancelled", async () => {
    confirmMock.mockResolvedValue(false)

    const envelope = baseEnvelope({ subject: "  " })
    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope,
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
      })
    )

    await act(async () => {
      await result.current.send({}, "  ")
    })

    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(apiFetchMock).not.toHaveBeenCalled()
    expect(envelope.resetDirty).not.toHaveBeenCalled()
  })

  it("guards against synchronous double-send on the empty-email path", async () => {
    apiFetchMock.mockResolvedValue(undefined)

    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope: baseEnvelope({ subject: "" }),
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
      })
    )

    await act(async () => {
      void result.current.send({}, "")
      void result.current.send({}, "")
    })

    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it("skips the confirmation when attachments are present", async () => {
    apiFetchMock.mockResolvedValue(undefined)

    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope: baseEnvelope({ subject: "" }),
        hasAttachments: true,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
      })
    )

    await act(async () => {
      await result.current.send({}, "")
    })

    expect(confirmMock).not.toHaveBeenCalled()
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it("skips the confirmation when the body is non-empty", async () => {
    apiFetchMock.mockResolvedValue(undefined)

    const { result } = renderHook(() =>
      useSender({
        sendUrl: SEND_URL,
        canReply: true,
        cannotSendReason: null,
        envelope: baseEnvelope({ subject: "" }),
        hasAttachments: false,
        mailboxIndexUrl: MAILBOX_INDEX_URL,
      })
    )

    await act(async () => {
      await result.current.send({}, "Body markdown")
    })

    expect(confirmMock).not.toHaveBeenCalled()
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })
})
