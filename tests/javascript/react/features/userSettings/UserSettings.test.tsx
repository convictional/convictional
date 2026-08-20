import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))
vi.mock("~/react/composites/confirmationDialog/confirm", () => ({ confirm: vi.fn() }))

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { UserSettings } from "~/react/features/userSettings/UserSettings"
import type { GmailConnection, Profile, SlackConnection } from "~/react/features/userSettings/types"
import { apiFetch } from "~/react/shared/apiFetch"
import type { CalendarResponse } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"

const mockedFetch = vi.mocked(apiFetch)
const mockedFlash = vi.mocked(showFlash)
const mockedConfirm = vi.mocked(confirm)

const PROFILE: Profile = {
  name: "Ada Lovelace",
  bio: "Mathematician.",
  time_zone: "America/New_York",
  picture: "https://cdn.example.com/ada.png",
  has_custom_avatar: true,
}
const CALENDAR: CalendarResponse = {
  calendar_connected: true,
  provider: "google",
  preference: "none",
  calendar_user_id: "cal_1",
  is_google_authenticated: true,
}

interface Overrides {
  profile?: Profile
  gmail?: GmailConnection["status"]
  slack?: SlackConnection["status"]
  calendar?: CalendarResponse
  notionConnected?: boolean
}

// Routes the per-section fetches and mutations by URL + method. PATCH/POST echo
// their input back as the updated resource, mirroring the real API.
function routeFetch({
  profile = PROFILE,
  gmail = "connected",
  slack = "connected",
  calendar = CALENDAR,
  notionConnected = true,
}: Overrides = {}) {
  let currentProfile = profile
  let currentCalendar = calendar
  mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET"
    if (url === "/api/users/me/profile" && method === "GET") return currentProfile
    if (url === "/api/users/me/profile" && method === "PATCH") {
      currentProfile = { ...currentProfile, ...JSON.parse(init!.body as string) }
      return currentProfile
    }
    if (url === "/api/users/me/profile/avatar" && method === "POST") {
      currentProfile = { ...currentProfile, picture: "https://cdn.example.com/new.png", has_custom_avatar: true }
      return currentProfile
    }
    if (url === "/api/users/me/profile/avatar" && method === "DELETE") {
      currentProfile = { ...currentProfile, picture: null, has_custom_avatar: false }
      return null
    }
    if (url === "/api/integrations/gmail/connection" && method === "GET") return { status: gmail }
    if (url === "/api/integrations/gmail/connection" && method === "DELETE") return null
    if (url === "/api/integrations/slack/connection" && method === "GET") return { status: slack }
    if (url === "/api/integrations/slack/connection" && method === "DELETE") return null
    if (url === "/api/users/me/calendar" && method === "GET") return currentCalendar
    if (url === "/api/users/me/calendar" && method === "PATCH") {
      currentCalendar = { ...currentCalendar, ...JSON.parse(init!.body as string) }
      return currentCalendar
    }
    if (url === "/api/users/me/calendar" && method === "DELETE") {
      currentCalendar = { ...currentCalendar, calendar_connected: false }
      return null
    }
    if (url === "/api/integrations/notion/connection") return { is_connected: notionConnected }
    // refreshCurrentUser after a profile change.
    if (url === "/api/users/me") return { id: "u1", display_name: "Ada", picture: null }
    throw new Error(`unexpected fetch: ${method} ${url}`)
  })
}

function renderSettings(props: { hasGoogleOauth?: boolean; slackAppInstallUrl?: string } = {}) {
  return render(
    <UserSettings
      hasGoogleOauth={props.hasGoogleOauth ?? true}
      slackAppInstallUrl={props.slackAppInstallUrl ?? "https://slack.com/oauth/install"}
    />
  )
}

// The section title renders synchronously; its body fetches independently. Scope
// to a section so the three "Disconnect" buttons don't collide.
function section(title: string): HTMLElement {
  return screen.getByText(title).closest("section") as HTMLElement
}

beforeEach(() => {
  mockedFetch.mockReset()
  mockedFlash.mockReset()
  mockedConfirm.mockReset()
  mockedConfirm.mockResolvedValue(true)
  // jsdom doesn't implement object URLs; AvatarUploader uses them for previews.
  URL.createObjectURL = vi.fn(() => "blob:preview")
  URL.revokeObjectURL = vi.fn()
  Object.defineProperty(window, "location", {
    value: { assign: vi.fn(), href: "" },
    writable: true,
    configurable: true,
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("UserSettings", () => {
  test("renders fields and section status from the GET payloads", async () => {
    routeFetch()
    renderSettings()

    expect(await screen.findByLabelText("Name")).toHaveValue("Ada Lovelace")
    expect(screen.getByLabelText("Job description")).toHaveValue("Mathematician.")
    expect(screen.getByLabelText("Timezone")).toHaveValue("America/New_York")
    // Section bodies fetch independently, so await them.
    expect(await screen.findByText("Your Gmail is connected for collaborative email.")).toBeInTheDocument()
    expect(await screen.findByText("Slack is connected.")).toBeInTheDocument()
    expect(await screen.findByText("Notion is connected.")).toBeInTheDocument()
    // Calendar connected → preference select reflects the server value.
    expect(await screen.findByLabelText("Automatic meeting recording")).toHaveValue("none")
  })

  test("hides the Gmail section when Google OAuth is not configured", async () => {
    routeFetch()
    renderSettings({ hasGoogleOauth: false })

    await screen.findByLabelText("Name")
    expect(screen.queryByText("Gmail")).toBeNull()
    expect(mockedFetch).not.toHaveBeenCalledWith("/api/integrations/gmail/connection", expect.anything())
  })

  test("saving the name PATCHes the profile and flashes success", async () => {
    routeFetch()
    renderSettings()

    const nameInput = await screen.findByLabelText("Name")
    fireEvent.change(nameInput, { target: { value: "Ada B. Lovelace" } })
    const form = nameInput.closest("form") as HTMLFormElement
    fireEvent.click(within(form).getByRole("button", { name: "Save" }))

    await waitFor(() =>
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/users/me/profile",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ name: "Ada B. Lovelace" }) })
      )
    )
    await waitFor(() => expect(mockedFlash).toHaveBeenCalledWith("Your name has been saved.", "success"))
  })

  test("saving the bio PATCHes the profile", async () => {
    routeFetch()
    renderSettings()

    const bio = await screen.findByLabelText("Job description")
    fireEvent.change(bio, { target: { value: "Wrote the first algorithm." } })
    const form = bio.closest("form") as HTMLFormElement
    fireEvent.click(within(form).getByRole("button", { name: "Save" }))

    await waitFor(() =>
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/users/me/profile",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ bio: "Wrote the first algorithm." }) })
      )
    )
  })

  test("saving the timezone PATCHes the profile", async () => {
    routeFetch()
    renderSettings()

    const select = await screen.findByLabelText("Timezone")
    fireEvent.change(select, { target: { value: "Europe/London" } })
    const form = select.closest("form") as HTMLFormElement
    fireEvent.click(within(form).getByRole("button", { name: "Save" }))

    await waitFor(() =>
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/users/me/profile",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ time_zone: "Europe/London" }) })
      )
    )
  })

  test("preselects the browser timezone when none is set, even when uncurated", async () => {
    vi.spyOn(Intl, "DateTimeFormat").mockReturnValue({
      resolvedOptions: () => ({ timeZone: "America/Indiana/Indianapolis" }),
    } as unknown as Intl.DateTimeFormat)
    routeFetch({ profile: { ...PROFILE, time_zone: null } })
    renderSettings()

    const select = (await screen.findByLabelText("Timezone")) as HTMLSelectElement
    expect(select.value).toBe("America/Indiana/Indianapolis")
    // The uncurated zone is prepended as its own option so it can be shown/selected.
    expect(within(select).getByRole("option", { name: "America/Indiana/Indianapolis" })).toBeInTheDocument()
  })

  test("uploading an avatar POSTs a FormData body", async () => {
    routeFetch()
    const { container } = renderSettings()
    await screen.findByLabelText("Name")

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(["x"], "me.png", { type: "image/png" })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      const call = mockedFetch.mock.calls.find(([url]) => url === "/api/users/me/profile/avatar")
      expect(call).toBeTruthy()
      expect(call![1]?.method).toBe("POST")
      expect(call![1]?.body).toBeInstanceOf(FormData)
    })
    await waitFor(() => expect(mockedFlash).toHaveBeenCalledWith("Your picture has been updated.", "success"))
  })

  test("Reset DELETEs the avatar and disappears once there is no custom avatar", async () => {
    routeFetch()
    renderSettings()

    fireEvent.click(await screen.findByRole("button", { name: "Reset" }))

    await waitFor(() =>
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/users/me/profile/avatar",
        expect.objectContaining({ method: "DELETE" })
      )
    )
    // After the refetch reports has_custom_avatar=false, the Reset affordance is gone.
    await waitFor(() => expect(screen.queryByRole("button", { name: "Reset" })).toBeNull())
  })

  describe("Gmail section", () => {
    test("Connect navigates (full document) and does not fetch", async () => {
      routeFetch({ gmail: "disconnected" })
      renderSettings()

      fireEvent.click(await screen.findByRole("button", { name: "Connect Gmail" }))
      expect(window.location.assign).toHaveBeenCalledWith("/integrations/gmail/auth")
      expect(mockedFetch).not.toHaveBeenCalledWith(
        "/api/integrations/gmail/connection",
        expect.objectContaining({ method: "POST" })
      )
    })

    test("shows the sign-in message when Gmail is unavailable", async () => {
      routeFetch({ gmail: "unavailable" })
      renderSettings()

      expect(await screen.findByText(/Sign in with Google to connect your Gmail/)).toBeInTheDocument()
      expect(screen.queryByRole("button", { name: "Connect Gmail" })).toBeNull()
    })

    test("Disconnect confirms, DELETEs, and flips to disconnected", async () => {
      routeFetch({ gmail: "connected" })
      renderSettings()

      await screen.findByLabelText("Name")
      const gmail = within(section("Gmail"))
      fireEvent.click(await gmail.findByRole("button", { name: "Disconnect" }))

      await waitFor(() =>
        expect(mockedFetch).toHaveBeenCalledWith(
          "/api/integrations/gmail/connection",
          expect.objectContaining({ method: "DELETE" })
        )
      )
      await waitFor(() => expect(gmail.getByRole("button", { name: "Connect Gmail" })).toBeInTheDocument())
    })
  })

  describe("Slack section", () => {
    test("Connect navigates to the Slack OAuth route", async () => {
      routeFetch({ slack: "disconnected" })
      renderSettings()

      fireEvent.click(await screen.findByRole("button", { name: "Connect Slack" }))
      expect(window.location.assign).toHaveBeenCalledWith("/integrations/slack/connect")
    })

    test("shows the ask-an-admin copy with an install link when unavailable", async () => {
      routeFetch({ slack: "unavailable" })
      renderSettings({ slackAppInstallUrl: "https://slack.com/oauth/install" })

      const link = await screen.findByRole("link", { name: "install Convictional on Slack" })
      expect(link).toHaveAttribute("href", "https://slack.com/oauth/install")
    })
  })

  describe("Calendar section", () => {
    test("changing the preference PATCHes the calendar", async () => {
      routeFetch()
      renderSettings()

      const select = await screen.findByLabelText("Automatic meeting recording")
      fireEvent.change(select, { target: { value: "all" } })

      await waitFor(() =>
        expect(mockedFetch).toHaveBeenCalledWith(
          "/api/users/me/calendar",
          expect.objectContaining({ method: "PATCH", body: JSON.stringify({ preference: "all" }) })
        )
      )
    })

    test("Connect navigates with a return_to back to the profile", async () => {
      routeFetch({ calendar: { ...CALENDAR, calendar_connected: false } })
      renderSettings()

      fireEvent.click(await screen.findByRole("button", { name: "Connect Google Calendar" }))
      expect(window.location.assign).toHaveBeenCalledWith(
        `/integrations/google_calendar/login?return_to=${encodeURIComponent("/profile/edit")}`
      )
    })

    test("shows the auth-method message for non-Google users", async () => {
      routeFetch({ calendar: { ...CALENDAR, calendar_connected: false, is_google_authenticated: false } })
      renderSettings()

      expect(await screen.findByText(/Calendar integration is not supported/)).toBeInTheDocument()
    })

    test("Disconnect DELETEs and flips to the connect prompt without a refetch", async () => {
      routeFetch()
      renderSettings()

      await screen.findByLabelText("Name")
      const calendar = within(section("Calendar and Meeting Recording"))
      fireEvent.click(await calendar.findByRole("button", { name: "Disconnect" }))

      await waitFor(() =>
        expect(mockedFetch).toHaveBeenCalledWith(
          "/api/users/me/calendar",
          expect.objectContaining({ method: "DELETE" })
        )
      )
      // Local flip (no GET refetch) → the connect prompt replaces the controls.
      await waitFor(() =>
        expect(calendar.getByRole("button", { name: "Connect Google Calendar" })).toBeInTheDocument()
      )
      const calendarGets = mockedFetch.mock.calls.filter(
        ([url, init]) => url === "/api/users/me/calendar" && (init?.method ?? "GET") === "GET"
      )
      expect(calendarGets).toHaveLength(1) // the initial mount fetch only
    })

    test("shows an error state (not an infinite spinner) when the calendar fetch fails", async () => {
      routeFetch()
      // Override just the calendar GET to fail; everything else still resolves.
      mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
        if (url === "/api/users/me/calendar" && (init?.method ?? "GET") === "GET") throw new Error("boom")
        if (url === "/api/users/me/profile") return PROFILE
        if (url === "/api/integrations/gmail/connection") return { status: "connected" }
        if (url === "/api/integrations/slack/connection") return { status: "connected" }
        if (url === "/api/integrations/notion/connection") return { is_connected: true }
        if (url === "/api/users/me") return { id: "u1", display_name: "Ada", picture: null }
        throw new Error(`unexpected fetch: ${url}`)
      })
      renderSettings()

      expect(await screen.findByText("Could not load your calendar connection.")).toBeInTheDocument()
    })
  })

  describe("Notion section", () => {
    test("renders the not-connected line and navigates to Manage Notion", async () => {
      routeFetch({ notionConnected: false })
      renderSettings()

      expect(await screen.findByText("Not connected.")).toBeInTheDocument()
      fireEvent.click(screen.getByRole("button", { name: "Manage Notion" }))
      expect(window.location.assign).toHaveBeenCalledWith("/integrations/notion/settings")
    })
  })

  test("renders an error state when the profile load fails", async () => {
    mockedFetch.mockImplementation(async (url: string) => {
      if (url === "/api/users/me/profile") throw new Error("boom")
      return null
    })
    renderSettings()

    expect(await screen.findByText("Could not load your settings.")).toBeInTheDocument()
  })
})
