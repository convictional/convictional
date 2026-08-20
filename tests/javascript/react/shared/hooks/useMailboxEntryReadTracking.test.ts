import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"
import { useMailboxEntryReadTracking } from "~/react/shared/hooks/useMailboxEntryReadTracking"

const mockedFetch = vi.mocked(apiFetch)

const CURRENT_USER = "user-self"
const OTHER_USER = "user-other"
const ENTRY_ID = "entry-1"

function setVisibility(state: DocumentVisibilityState): void {
  Object.defineProperty(document, "visibilityState", { value: state, configurable: true })
}

function fireVisibilityChange(state: DocumentVisibilityState): void {
  setVisibility(state)
  document.dispatchEvent(new Event("visibilitychange"))
}

afterEach(() => {
  mockedFetch.mockReset()
  setVisibility("visible")
})

// Exercised with the post island's configuration; chat's configuration is covered
// by the chat island's own tests.
describe("useMailboxEntryReadTracking (post configuration)", () => {
  test("does not mark read on mount", () => {
    setVisibility("visible")
    renderHook(() =>
      useMailboxEntryReadTracking({
        mailboxEntryId: ENTRY_ID,
        currentUserId: CURRENT_USER,
        enabled: true,
        flushOnUnmount: "when-pending",
      })
    )

    expect(mockedFetch).not.toHaveBeenCalled()
  })

  test("marks read on an incoming comment from another user while visible", () => {
    mockedFetch.mockResolvedValue(undefined)
    setVisibility("visible")
    const { result } = renderHook(() =>
      useMailboxEntryReadTracking({
        mailboxEntryId: ENTRY_ID,
        currentUserId: CURRENT_USER,
        enabled: true,
        flushOnUnmount: "when-pending",
      })
    )

    act(() => result.current.notifyIncoming(OTHER_USER))

    expect(mockedFetch).toHaveBeenCalledWith(`/api/mailbox_entries/${ENTRY_ID}/mark_read`, { method: "POST" })
    expect(mockedFetch).toHaveBeenCalledTimes(1)
  })

  test("does not mark read for the viewer's own comment", () => {
    setVisibility("visible")
    const { result } = renderHook(() =>
      useMailboxEntryReadTracking({
        mailboxEntryId: ENTRY_ID,
        currentUserId: CURRENT_USER,
        enabled: true,
        flushOnUnmount: "when-pending",
      })
    )

    act(() => result.current.notifyIncoming(CURRENT_USER))

    expect(mockedFetch).not.toHaveBeenCalled()
  })

  test("defers while hidden and marks read once on visibility change", () => {
    mockedFetch.mockResolvedValue(undefined)
    setVisibility("hidden")
    const { result } = renderHook(() =>
      useMailboxEntryReadTracking({
        mailboxEntryId: ENTRY_ID,
        currentUserId: CURRENT_USER,
        enabled: true,
        flushOnUnmount: "when-pending",
      })
    )

    act(() => result.current.notifyIncoming(OTHER_USER))
    expect(mockedFetch).not.toHaveBeenCalled()

    act(() => fireVisibilityChange("visible"))
    expect(mockedFetch).toHaveBeenCalledTimes(1)

    // A second visibility change with nothing pending does not re-POST.
    act(() => fireVisibilityChange("visible"))
    expect(mockedFetch).toHaveBeenCalledTimes(1)
  })

  test("flushes a pending read once on unmount when a comment arrived hidden", () => {
    mockedFetch.mockResolvedValue(undefined)
    setVisibility("hidden")
    const { result, unmount } = renderHook(() =>
      useMailboxEntryReadTracking({
        mailboxEntryId: ENTRY_ID,
        currentUserId: CURRENT_USER,
        enabled: true,
        flushOnUnmount: "when-pending",
      })
    )

    act(() => result.current.notifyIncoming(OTHER_USER))
    expect(mockedFetch).not.toHaveBeenCalled()

    unmount()
    expect(mockedFetch).toHaveBeenCalledTimes(1)
  })

  test("does not flush on a quiet unmount", () => {
    setVisibility("visible")
    const { unmount } = renderHook(() =>
      useMailboxEntryReadTracking({
        mailboxEntryId: ENTRY_ID,
        currentUserId: CURRENT_USER,
        enabled: true,
        flushOnUnmount: "when-pending",
      })
    )

    unmount()
    expect(mockedFetch).not.toHaveBeenCalled()
  })

  test("never POSTs when there is no mailbox entry", () => {
    setVisibility("visible")
    const { result } = renderHook(() =>
      useMailboxEntryReadTracking({
        mailboxEntryId: null,
        currentUserId: CURRENT_USER,
        enabled: true,
        flushOnUnmount: "when-pending",
      })
    )

    act(() => result.current.notifyIncoming(OTHER_USER))

    expect(mockedFetch).not.toHaveBeenCalled()
  })

  test("never POSTs when disabled", () => {
    setVisibility("visible")
    const { result } = renderHook(() =>
      useMailboxEntryReadTracking({
        mailboxEntryId: ENTRY_ID,
        currentUserId: CURRENT_USER,
        enabled: false,
        flushOnUnmount: "when-pending",
      })
    )

    act(() => result.current.notifyIncoming(OTHER_USER))

    expect(mockedFetch).not.toHaveBeenCalled()
  })
})
