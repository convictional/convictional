import { act, fireEvent, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { MailboxActionBar } from "~/react/composites/MailboxActionBar"
import type { MailboxActionUrls, MailboxState } from "~/react/composites/MailboxActionBar"

import { resetCurrentUser, setCurrentUser } from "../shared/currentUserFixtures"
import { cleanup, render, screen } from "../shared/testUtils"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

// No channel-backed live updates here; resolve the hook to the null it would
// return anyway, without the "not available at mount" warning.
vi.mock("~/react/shared/hooks/useChannelsClient", () => ({ useChannelsClient: () => null }))
vi.mock("~/shared/flash", () => ({
  showFlash: vi.fn(),
  queueFlash: vi.fn(),
}))

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { showFlash } from "~/shared/flash"

const mockedFetch = vi.mocked(apiFetch)
const mockedFlash = vi.mocked(showFlash)

const URLS: MailboxActionUrls = {
  archive: "/api/mailbox_entries/abc/archive",
  unarchive: "/api/mailbox_entries/abc/unarchive",
  markRead: "/api/mailbox_entries/abc/mark_read",
  markUnread: "/api/mailbox_entries/abc/mark_unread",
  snooze: "/api/mailbox_entries/abc/snooze",
  unsnooze: "/api/mailbox_entries/abc/unsnooze",
}

const BACK = { url: "/inbox", label: "Back to inbox" }

const DEFAULT_STATE: MailboxState = {
  isUnread: true,
  isArchived: false,
  isSnoozed: false,
  snoozedUntil: null,
}

const observers: Array<{
  callback: IntersectionObserverCallback
  observe: ReturnType<typeof vi.fn>
  disconnect: ReturnType<typeof vi.fn>
}> = []

function fireIntersect(visible: boolean): void {
  for (const o of observers) {
    o.callback([{ isIntersecting: visible } as IntersectionObserverEntry], {} as IntersectionObserver)
  }
}

const originalLocation = window.location

beforeEach(() => {
  observers.length = 0
  // Seed the singleton cache so useCurrentUser() (for the snooze-confirmation tz)
  // reads without firing an unmocked /api/users/me fetch.
  setCurrentUser({ id: "viewer-1" })
  vi.stubGlobal(
    "IntersectionObserver",
    vi.fn(function (cb: IntersectionObserverCallback) {
      const observer = { callback: cb, observe: vi.fn(), disconnect: vi.fn() }
      observers.push(observer)
      return { observe: observer.observe, disconnect: observer.disconnect, unobserve: vi.fn(), takeRecords: vi.fn() }
    })
  )
})

afterEach(() => {
  cleanup()
  resetCurrentUser()
  vi.unstubAllGlobals()
  Object.defineProperty(window, "location", { value: originalLocation, writable: true, configurable: true })
  mockedFetch.mockReset()
  mockedFlash.mockClear()
})

describe("MailboxActionBar", () => {
  test("optimistically marks read and rolls back on failure", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError(500, { detail: "boom" }))

    render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} />)

    fireEvent.click(screen.getByLabelText("Mark read"))
    expect(screen.getByLabelText("Mark unread")).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByLabelText("Mark read")).toBeInTheDocument()
    })
    expect(mockedFlash).toHaveBeenCalledWith("Couldn't mark as read.")
  })

  test("dispatches thread-marked-read on successful mark read", async () => {
    mockedFetch.mockResolvedValueOnce(undefined)
    const listener = vi.fn()
    window.addEventListener("thread-marked-read", listener)

    render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} />)
    fireEvent.click(screen.getByLabelText("Mark read"))

    await waitFor(() => expect(listener).toHaveBeenCalled())
    window.removeEventListener("thread-marked-read", listener)
  })

  test("auto-mark-read fires once per mount across visibility toggles", async () => {
    vi.useFakeTimers()
    mockedFetch.mockResolvedValue(undefined)

    render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} />)

    fireIntersect(true)
    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(mockedFetch).toHaveBeenCalledWith(URLS.markRead, { method: "POST" })
    expect(mockedFetch).toHaveBeenCalledTimes(1)

    fireIntersect(false)
    fireIntersect(true)
    await act(async () => {
      vi.advanceTimersByTime(2000)
    })
    expect(mockedFetch).toHaveBeenCalledTimes(1)

    vi.useRealTimers()
  })

  test("auto-mark-read does not fire if visibility lost before delay elapses", async () => {
    vi.useFakeTimers()
    mockedFetch.mockResolvedValue(undefined)

    render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} />)

    fireIntersect(true)
    await act(async () => {
      vi.advanceTimersByTime(500)
    })
    fireIntersect(false)
    await act(async () => {
      vi.advanceTimersByTime(2000)
    })
    expect(mockedFetch).not.toHaveBeenCalled()

    vi.useRealTimers()
  })

  test("snooze popover opens on click and closes on Escape", async () => {
    render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} />)

    fireEvent.click(screen.getByLabelText("Snooze"))
    expect(screen.getByRole("menu")).toBeInTheDocument()

    fireEvent.keyDown(document.activeElement || document.body, { key: "Escape" })
    await waitFor(() => {
      expect(screen.queryByRole("menu")).toBeNull()
    })
  })

  test("snooze preset POSTs and redirects to back.url", async () => {
    mockedFetch.mockResolvedValueOnce(undefined)
    const location = { href: "" }
    Object.defineProperty(window, "location", { value: location, writable: true })

    render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} />)
    fireEvent.click(screen.getByLabelText("Snooze"))

    const preset = await screen.findByRole("menuitem", { name: /two hours from now/i })
    fireEvent.click(preset)

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        URLS.snooze,
        expect.objectContaining({ method: "POST", body: expect.stringContaining('"snoozed_until"') })
      )
    })
    expect(location.href).toBe(BACK.url)
  })

  test("unsnooze updates state in place", async () => {
    mockedFetch.mockResolvedValueOnce(undefined)
    const snoozedState: MailboxState = {
      ...DEFAULT_STATE,
      isUnread: false,
      isSnoozed: true,
      snoozedUntil: "2030-01-01T09:00:00Z",
    }

    render(<MailboxActionBar state={snoozedState} actionUrls={URLS} back={BACK} />)
    fireEvent.click(screen.getByLabelText("Unsnooze"))

    await waitFor(() => {
      expect(screen.getByLabelText("Snooze")).toBeInTheDocument()
    })
  })

  test("unarchive updates state in place without navigation", async () => {
    mockedFetch.mockResolvedValueOnce(undefined)
    const archivedState: MailboxState = { ...DEFAULT_STATE, isArchived: true }

    render(<MailboxActionBar state={archivedState} actionUrls={URLS} back={BACK} />)
    fireEvent.click(screen.getByLabelText("Unarchive"))

    await waitFor(() => {
      expect(screen.getByLabelText("Archive")).toBeInTheDocument()
    })
  })

  test("renders trailingSlot", () => {
    render(
      <MailboxActionBar
        state={DEFAULT_STATE}
        actionUrls={URLS}
        back={BACK}
        trailingSlot={<div data-testid="extra">extra</div>}
      />
    )
    expect(screen.getByTestId("extra")).toBeInTheDocument()
  })

  test("archive redirects to back.url on success", async () => {
    mockedFetch.mockResolvedValueOnce(undefined)
    const location = { href: "" }
    Object.defineProperty(window, "location", { value: location, writable: true })

    render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} />)
    fireEvent.click(screen.getByLabelText("Archive"))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(URLS.archive, { method: "POST" })
    })
    expect(location.href).toBe(BACK.url)
  })

  test("mark unread POSTs and redirects to back.url", async () => {
    mockedFetch.mockResolvedValueOnce(undefined)
    const location = { href: "" }
    Object.defineProperty(window, "location", { value: location, writable: true })
    const listener = vi.fn()
    window.addEventListener("thread-marked-unread", listener)

    const readState: MailboxState = { ...DEFAULT_STATE, isUnread: false }
    render(<MailboxActionBar state={readState} actionUrls={URLS} back={BACK} />)
    fireEvent.click(screen.getByLabelText("Mark unread"))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(URLS.markUnread, { method: "POST" })
    })
    expect(listener).toHaveBeenCalled()
    expect(location.href).toBe(BACK.url)
    window.removeEventListener("thread-marked-unread", listener)
  })

  test("onStateChange fires with next state for mark read", async () => {
    mockedFetch.mockResolvedValue(undefined)
    const onStateChange = vi.fn()

    render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} onStateChange={onStateChange} />)

    fireEvent.click(screen.getByLabelText("Mark read"))
    expect(onStateChange).toHaveBeenLastCalledWith({ ...DEFAULT_STATE, isUnread: false })
  })

  test("syncs local state when the state prop changes", () => {
    const { rerender } = render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} />)
    expect(screen.getByLabelText("Mark read")).toBeInTheDocument()

    rerender(<MailboxActionBar state={{ ...DEFAULT_STATE, isUnread: false }} actionUrls={URLS} back={BACK} />)
    expect(screen.getByLabelText("Mark unread")).toBeInTheDocument()
  })
})

// The email thread (EmailThreadShow) renders this action bar, so these are the
// thread's keyboard shortcuts. Unlike the click-based tests above, these press a
// real key: fireEvent.keyDown dispatches a bubbling KeyboardEvent that reaches
// @github/hotkey's document listener, which synthesizes a click on the hidden
// [data-hotkey] button — the exact runtime path. @github/hotkey is NOT stubbed.
function pressKey(key: string) {
  fireEvent.keyDown(document.body, { key })
}

describe("MailboxActionBar hotkey bindings (real @github/hotkey)", () => {
  test("pressing 'e' archives the thread and redirects to back.url", async () => {
    mockedFetch.mockResolvedValueOnce(undefined)
    const location = { href: "" }
    Object.defineProperty(window, "location", { value: location, writable: true })

    render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} />)

    pressKey("e")

    await waitFor(() => expect(mockedFetch).toHaveBeenCalledWith(URLS.archive, { method: "POST" }))
    expect(location.href).toBe(BACK.url)
  })

  test("'e' is disabled while the snooze popover is open", async () => {
    render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} />)

    // Opening snooze flips useHotkeyInstall's `enabled` to false, uninstalling
    // the archive hotkey so `e` dismisses the popover instead of archiving.
    fireEvent.click(screen.getByLabelText("Snooze"))
    expect(screen.getByRole("menu")).toBeInTheDocument()

    pressKey("e")

    expect(mockedFetch).not.toHaveBeenCalledWith(URLS.archive, expect.anything())
  })

  // Contract test: pins the thread's data-hotkey set. Today only archive ('e')
  // is bound here; Mark read / Mark unread have NO keyboard shortcut. If that
  // changes (intentionally or not), this test fails and forces a decision.
  test("only archive carries a data-hotkey; mark read/unread do not", () => {
    render(<MailboxActionBar state={DEFAULT_STATE} actionUrls={URLS} back={BACK} />)

    expect(screen.getByLabelText("Archive")).toHaveAttribute("data-hotkey", "e")
    expect(screen.getByLabelText("Mark read")).not.toHaveAttribute("data-hotkey")
  })
})
