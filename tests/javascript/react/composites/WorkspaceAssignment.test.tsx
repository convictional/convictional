import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { User } from "~/react/shared/types"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

vi.mock("~/react/shared/hooks/useOrganizationMembers", () => ({
  useOrganizationMembers: vi.fn(),
}))

import { apiFetch } from "~/react/shared/apiFetch"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import { WorkspaceAssignment } from "~/react/composites/WorkspaceAssignment"

import { cleanup, fireEvent, render, screen, waitFor, within } from "../shared/testUtils"

const mockedFetch = vi.mocked(apiFetch)
const mockedMembers = vi.mocked(useOrganizationMembers)

const USERS: User[] = [
  { id: "u1", display_name: "Alice Anderson", picture: null },
  { id: "u2", display_name: "Bob Baker", picture: null },
  { id: "u3", display_name: "Carol Carter", picture: null },
]

const WORKSPACE_ID = "ws-1"

function setMembers(users: User[] = USERS) {
  mockedMembers.mockReturnValue({ users, groups: [], loading: false, error: null })
}

beforeEach(() => {
  setMembers()
})

afterEach(() => {
  cleanup()
  mockedFetch.mockReset()
  vi.clearAllMocks()
  delete document.documentElement.dataset.isMobile
})

describe("WorkspaceAssignment (desktop)", () => {
  test("searches and assigns a member, then unassigns the current assignee", async () => {
    // First mount: unassigned.
    mockedFetch.mockResolvedValueOnce({ assignee: null })
    render(<WorkspaceAssignment workspaceId={WORKSPACE_ID} />)

    const trigger = await screen.findByLabelText("Assign")
    fireEvent.click(trigger)

    const search = screen.getByPlaceholderText("Search people…")
    expect(search).toBeInTheDocument()
    expect(screen.getByText("Alice Anderson")).toBeInTheDocument()
    expect(screen.getByText("Bob Baker")).toBeInTheDocument()

    // Filtering narrows to the matching member and drops the rest (both directions).
    fireEvent.change(search, { target: { value: "bob" } })
    expect(screen.getByText("Bob Baker")).toBeInTheDocument()
    expect(screen.queryByText("Alice Anderson")).toBeNull()

    mockedFetch.mockResolvedValueOnce({ assignee: USERS[1] })
    fireEvent.click(screen.getByText("Bob Baker"))

    await waitFor(() =>
      expect(mockedFetch).toHaveBeenCalledWith(
        `/api/workspaces/${WORKSPACE_ID}/assignment`,
        expect.objectContaining({ method: "PATCH" })
      )
    )
    const patchInit = mockedFetch.mock.calls.find(c => (c[1] as RequestInit)?.method === "PATCH")?.[1] as RequestInit
    expect(JSON.parse(patchInit.body as string)).toEqual({ user_id: "u2" })

    // Fresh mount with an assignee already set via the initial GET.
    cleanup()
    mockedFetch.mockReset()
    mockedFetch.mockResolvedValueOnce({ assignee: USERS[1] })
    render(<WorkspaceAssignment workspaceId={WORKSPACE_ID} />)

    // The trigger surfaces the assignee's name.
    const assignedTrigger = await screen.findByLabelText("Assigned to Bob Baker")
    fireEvent.click(assignedTrigger)

    // The current assignee is surfaced in the header and filtered out of the list.
    expect(screen.getByText("Current Assignee")).toBeInTheDocument()
    const header = screen.getByText("Current Assignee").closest("div")!
    expect(within(header).getByText("Bob Baker")).toBeInTheDocument()

    mockedFetch.mockResolvedValueOnce(undefined)
    fireEvent.click(within(header).getByText("Bob Baker"))

    await waitFor(() =>
      expect(mockedFetch).toHaveBeenCalledWith(
        `/api/workspaces/${WORKSPACE_ID}/assignment`,
        expect.objectContaining({ method: "DELETE" })
      )
    )
  })
})

describe("WorkspaceAssignment (mobile)", () => {
  test("opens a bottom-sheet dialog and assigns a member", async () => {
    document.documentElement.dataset.isMobile = "true"
    mockedFetch.mockResolvedValueOnce({ assignee: null })
    render(<WorkspaceAssignment workspaceId={WORKSPACE_ID} />)

    const trigger = await screen.findByLabelText("Assign")
    fireEvent.click(trigger)

    const dialog = await screen.findByRole("dialog")
    expect(dialog).toBeInTheDocument()
    expect(within(dialog).getByPlaceholderText("Search people…")).toBeInTheDocument()

    mockedFetch.mockResolvedValueOnce({ assignee: USERS[0] })
    fireEvent.click(within(dialog).getByText("Alice Anderson"))

    await waitFor(() =>
      expect(mockedFetch).toHaveBeenCalledWith(
        `/api/workspaces/${WORKSPACE_ID}/assignment`,
        expect.objectContaining({ method: "PATCH" })
      )
    )
    const patchInit = mockedFetch.mock.calls.find(c => (c[1] as RequestInit)?.method === "PATCH")?.[1] as RequestInit
    expect(JSON.parse(patchInit.body as string)).toEqual({ user_id: "u1" })
  })
})
