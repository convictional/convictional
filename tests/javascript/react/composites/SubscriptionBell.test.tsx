import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"
import { SubscriptionBell } from "~/react/composites/SubscriptionBell"

const mockedFetch = vi.mocked(apiFetch)

const WORKSPACE_ID = "ws-1"

beforeEach(() => {
  mockedFetch.mockReset()
})

afterEach(() => {
  cleanup()
})

async function openDropdown() {
  fireEvent.click(screen.getByLabelText("Subscription preferences"))
  await screen.findByRole("menu")
}

describe("SubscriptionBell", () => {
  test("loads state, shows Default checked when no row exists, and bell shows notifications_off when not subscribed", async () => {
    mockedFetch.mockResolvedValueOnce({ wants_all: false, is_explicit: false })
    render(<SubscriptionBell workspaceId={WORKSPACE_ID} />)

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(`/api/workspaces/${WORKSPACE_ID}/subscription`)
    })

    expect(screen.getByText("notifications_off")).toBeInTheDocument()

    await openDropdown()

    const defaultOption = screen.getByRole("button", { name: /radio_button_checked Default/ })
    expect(defaultOption).toBeInTheDocument()
  })

  test("clicking All writes a SUBSCRIBED row, dropdown stays open, bell flips to notifications", async () => {
    mockedFetch.mockResolvedValueOnce({ wants_all: true, is_explicit: false }) // initial
    mockedFetch.mockResolvedValueOnce({ wants_all: true, is_explicit: true }) // after PATCH

    render(<SubscriptionBell workspaceId={WORKSPACE_ID} />)
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    await openDropdown()
    fireEvent.click(screen.getByRole("button", { name: /Every comment and update/ }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        `/api/workspaces/${WORKSPACE_ID}/subscription`,
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ level: "all" }) })
      )
    })

    expect(screen.getByRole("menu")).toBeInTheDocument()
    expect(screen.getByText("notifications")).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /radio_button_checked All/ })).toBeInTheDocument()
    })
  })

  test("clicking Relevant to me writes RELEVANT_ONLY row", async () => {
    mockedFetch.mockResolvedValueOnce({ wants_all: true, is_explicit: false })
    mockedFetch.mockResolvedValueOnce({ wants_all: false, is_explicit: true })

    render(<SubscriptionBell workspaceId={WORKSPACE_ID} />)
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    await openDropdown()
    fireEvent.click(screen.getByRole("button", { name: /Relevant to me/ }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        `/api/workspaces/${WORKSPACE_ID}/subscription`,
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ level: "relevant_only" }) })
      )
    })
    expect(screen.getByText("notifications_off")).toBeInTheDocument()
  })

  test("clicking Default deletes the row and re-fetches the fallback state", async () => {
    mockedFetch.mockResolvedValueOnce({ wants_all: false, is_explicit: true }) // initial GET
    mockedFetch.mockResolvedValueOnce(null) // DELETE returns 204 (no body)
    mockedFetch.mockResolvedValueOnce({ wants_all: true, is_explicit: false }) // follow-up GET

    render(<SubscriptionBell workspaceId={WORKSPACE_ID} />)
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    await openDropdown()
    fireEvent.click(screen.getByRole("button", { name: /Use your settings/ }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        `/api/workspaces/${WORKSPACE_ID}/subscription`,
        expect.objectContaining({ method: "DELETE" })
      )
    })
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(3))
    expect(mockedFetch).toHaveBeenLastCalledWith(`/api/workspaces/${WORKSPACE_ID}/subscription`)
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /radio_button_checked Default/ })
      ).toBeInTheDocument()
    })
  })

  test("subtitle prop renders the subtitle text above the menu", async () => {
    mockedFetch.mockResolvedValueOnce({ wants_all: true, is_explicit: false })
    render(<SubscriptionBell workspaceId={WORKSPACE_ID} subtitle="Announcements always reach you." />)
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    await openDropdown()
    expect(screen.getByText("Announcements always reach you.")).toBeInTheDocument()
    // Menu options still render — user can still adjust follow-ups.
    expect(screen.getByText("All")).toBeInTheDocument()
    expect(screen.getByText("Relevant to me")).toBeInTheDocument()
  })

  test("manageUrl prop renders a footer link to the settings page", async () => {
    mockedFetch.mockResolvedValueOnce({ wants_all: true, is_explicit: false })
    render(<SubscriptionBell workspaceId={WORKSPACE_ID} manageUrl="/notifications" />)
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    await openDropdown()
    const link = screen.getByRole("link", { name: /Manage notification settings/ })
    expect(link).toHaveAttribute("href", "/notifications")
  })

  test("manage link is omitted when manageUrl is not provided", async () => {
    mockedFetch.mockResolvedValueOnce({ wants_all: true, is_explicit: false })
    render(<SubscriptionBell workspaceId={WORKSPACE_ID} />)
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    await openDropdown()
    expect(screen.queryByRole("link", { name: /Manage/ })).toBeNull()
  })

  test("subtitle is omitted when not provided", async () => {
    mockedFetch.mockResolvedValueOnce({ wants_all: true, is_explicit: false })
    render(<SubscriptionBell workspaceId={WORKSPACE_ID} />)
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    await openDropdown()
    // No subtitle prop → no extra text block above the menu options.
    expect(screen.queryByText(/Announcements/)).toBeNull()
  })

  test("per-resource copy overrides individual option labels and hints", async () => {
    mockedFetch.mockResolvedValueOnce({ wants_all: false, is_explicit: false })
    render(
      <SubscriptionBell
        workspaceId={WORKSPACE_ID}
        options={{
          all: { hint: "Every reply on this post" },
          default: { hint: "Use your post settings" },
        }}
      />
    )
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    await openDropdown()
    expect(screen.getByText("Every reply on this post")).toBeInTheDocument()
    expect(screen.getByText("Use your post settings")).toBeInTheDocument()
    // The override-less option keeps its default hint
    expect(screen.getByText("@mentions only")).toBeInTheDocument()
  })
})
