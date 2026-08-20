import { cleanup, fireEvent, render, screen, waitFor, within } from "../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

// Stub the ProseMirror-backed system-prompt editor with a ref handle returning
// fixed content, so the save test doesn't need a real editor in JSDOM.
vi.mock("~/react/features/organizationSettings/components/SystemPromptEditor", async () => {
  const React = await vi.importActual<typeof import("react")>("react")
  return {
    SystemPromptEditor: React.forwardRef((_props, ref) => {
      React.useImperativeHandle(ref, () => ({ getContent: () => "edited system prompt" }))
      return React.createElement("div", { "data-testid": "system-prompt-editor" })
    }),
  }
})

import { apiFetch } from "~/react/shared/apiFetch"
import { queryClient } from "~/react/shared/queryClient"
import { OrganizationSettings } from "~/react/features/organizationSettings/OrganizationSettings"
import type { OrganizationData } from "~/react/features/organizationSettings/types"
import type { UpdatesConfiguration } from "~/react/composites/organizationUpdatesConfiguration/types"
import { showFlash } from "~/shared/flash"
import { setCurrentUser } from "../../shared/currentUserFixtures"

const mockedFetch = vi.mocked(apiFetch)
const mockedFlash = vi.mocked(showFlash)

const ORG: OrganizationData = { id: "org_1", name: "Acme", system_prompt: "Be helpful." }
const UPDATES: UpdatesConfiguration = {
  frequency: "weekly",
  hour: 9,
  day_of_week: "1",
  goal_update_question: "How's it going?",
  has_goals: true,
  enabled: true,
}

interface FetchOverrides {
  org?: OrganizationData
  updates?: UpdatesConfiguration
}

// Routes the concurrent mount fetches (org, updates-config) and PATCH saves by
// URL + method, echoing the PATCH body back as the updated resource.
function routeFetch({ org = ORG, updates = UPDATES }: FetchOverrides = {}) {
  mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET"
    const body = init?.body ? JSON.parse(init.body as string) : {}
    if (url === "/api/organization" && method === "GET") return org
    if (url === "/api/organization" && method === "PATCH") return { ...org, ...body }
    if (url === "/api/organization/updates_configuration") return updates
    throw new Error(`unexpected fetch: ${method} ${url}`)
  })
}

// is_admin / is_superuser now come from the current user (the route's beforeLoad
// admin-gates the page), so seed them on the user rather than passing props.
function renderSettings({ isAdmin = true, isSuperuser = true }: { isAdmin?: boolean; isSuperuser?: boolean } = {}) {
  setCurrentUser({ id: "u1", time_zone: "America/New_York", is_admin: isAdmin, is_superuser: isSuperuser })
  return render(<OrganizationSettings />)
}

beforeEach(() => {
  mockedFetch.mockReset()
  mockedFlash.mockReset()
})

afterEach(() => {
  cleanup()
  // Reset the shared singleton cache (org/updates queries + the seeded current
  // user) so each test starts cold and refetches through the mock.
  queryClient.clear()
})

describe("OrganizationSettings", () => {
  test("renders all three sections for a superuser admin", async () => {
    routeFetch()
    renderSettings()

    // Basics
    expect(await screen.findByLabelText("Name")).toHaveValue("Acme")
    // Updates configuration (the composite) owns its own fetch
    expect(await screen.findByLabelText("Frequency")).toBeInTheDocument()
    // System prompt
    expect(screen.getByText("Support Fields")).toBeInTheDocument()
    expect(screen.getByTestId("system-prompt-editor")).toBeInTheDocument()
  })

  test("hides the system-prompt section when not a superuser", async () => {
    routeFetch({ org: { id: "org_1", name: "Acme" } })
    renderSettings({ isSuperuser: false })

    await screen.findByLabelText("Name")
    expect(screen.queryByText("Support Fields")).toBeNull()
    expect(screen.queryByTestId("system-prompt-editor")).toBeNull()
  })

  test("saving the name PATCHes /api/organization and flashes success", async () => {
    routeFetch()
    renderSettings()

    const nameInput = await screen.findByLabelText("Name")
    const basicsForm = nameInput.closest("form") as HTMLFormElement
    fireEvent.change(nameInput, { target: { value: "Acme Corp" } })
    fireEvent.click(within(basicsForm).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/organization",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ name: "Acme Corp" }) })
      )
    })
    await waitFor(() => expect(mockedFlash).toHaveBeenCalledWith("Organization name saved.", "success"))
  })

  test("saving the system prompt PATCHes /api/organization with the editor content", async () => {
    routeFetch()
    renderSettings()

    const editor = await screen.findByTestId("system-prompt-editor")
    const promptForm = editor.closest("form") as HTMLFormElement
    fireEvent.click(within(promptForm).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/organization",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ system_prompt: "edited system prompt" }) })
      )
    })
    await waitFor(() => expect(mockedFlash).toHaveBeenCalledWith("System prompt saved.", "success"))
  })

  test("renders an error state when the organization load fails", async () => {
    mockedFetch.mockImplementation(async (url: string) => {
      if (url === "/api/organization") throw new Error("boom")
      return UPDATES
    })
    renderSettings()

    expect(await screen.findByText("Could not load organization settings.")).toBeInTheDocument()
  })
})
