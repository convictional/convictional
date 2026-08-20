import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { cleanup, render, screen, waitFor } from "../shared/testUtils"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"
import { queryClient } from "~/react/shared/queryClient"
import { GmailReauthBadge } from "~/react/composites/GmailReauthBadge"

const mockedFetch = vi.mocked(apiFetch)
const BADGE_TEXT = "Your Gmail account needs to be reconnected"

beforeEach(() => {
  mockedFetch.mockReset()
})

afterEach(() => {
  cleanup()
  queryClient.clear()
})

describe("GmailReauthBadge", () => {
  test("shows the reconnect nag with a full-navigation OAuth link when the connection needs reauth", async () => {
    mockedFetch.mockResolvedValueOnce({ status: "disconnected", requires_reauth: true })

    render(<GmailReauthBadge />)

    await waitFor(() => expect(mockedFetch).toHaveBeenCalledWith("/api/integrations/gmail/connection"))
    expect(await screen.findByText(BADGE_TEXT)).toBeInTheDocument()

    // A plain anchor (not a client-routed Link) so the cross-origin OAuth redirect
    // is a full-document navigation, carrying return_to back to the current path.
    const link = screen.getByRole("link", { name: /Connect Gmail/ })
    expect(link.getAttribute("href")).toMatch(/^\/integrations\/gmail\/auth\?return_to=/)
  })

  test("renders nothing when the connection does not need reauth", async () => {
    mockedFetch.mockResolvedValueOnce({ status: "connected", requires_reauth: false })

    const { container } = render(<GmailReauthBadge />)

    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))
    expect(screen.queryByText(BADGE_TEXT)).toBeNull()
    expect(container).toBeEmptyDOMElement()
  })
})
