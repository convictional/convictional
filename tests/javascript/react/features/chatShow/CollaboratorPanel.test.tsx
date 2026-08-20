import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { cleanup, fireEvent, render, screen, waitFor, within } from "../../shared/testUtils"
import { resetOrganizationMembers } from "../../shared/organizationMembersFixtures"

// The panel navigates (continue-in-existing-chat / group) via useNavigate; these
// tests don't exercise those paths, so a no-op navigate keeps the always-mounted
// Add view from needing a full RouterProvider.
vi.mock("@tanstack/react-router", async importActual => ({
  ...(await importActual<typeof import("@tanstack/react-router")>()),
  useNavigate: () => vi.fn(),
}))

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {},
}))

vi.mock("../../../../../app/javascript/react/ui/Avatar", () => ({
  Avatar: ({ displayName }: { displayName: string }) => (
    <span data-testid="avatar" data-name={displayName} aria-hidden="true" />
  ),
}))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { CollaboratorPanel } from "../../../../../app/javascript/react/features/chatShow/CollaboratorPanel"

const mockApi = vi.mocked(apiFetch)

const collaborators = [
  { id: "m1", user: { id: "u1", display_name: "Alice", picture: null } },
  { id: "m2", user: { id: "u2", display_name: "Me", picture: null } },
  { id: "m3", user: { id: "u3", display_name: "Carol", picture: null } },
]

beforeEach(() => {
  // The panel fetches org members on mount via useOrganizationMembers, so every
  // render hits this endpoint. Default to an empty-but-valid response; tests that
  // care about candidates override with their own mockImplementation.
  mockApi.mockResolvedValue({ users: [], groups: [] } as any)
})

afterEach(() => {
  cleanup()
  mockApi.mockReset()
  // Reset the shared org-members cache so warm data from one test doesn't suppress
  // the next test's fetch (the singleton query cache persists across tests).
  resetOrganizationMembers()
})

describe("CollaboratorPanel", () => {
  test("renders collaborators with remove affordance and close button", () => {
    const onClose = vi.fn()
    render(
      <CollaboratorPanel
        collaborators={collaborators}
        currentUserId="u2"
        onClose={onClose}
        onAdd={vi.fn()}
        onLeave={vi.fn(async () => ({}))}
      />
    )
    expect(screen.getByText("Alice")).toBeTruthy()
    expect(screen.getByText("Me")).toBeTruthy()
    expect(screen.getByText("Carol")).toBeTruthy()
    fireEvent.click(screen.getByLabelText("Close members panel"))
    // Closing runs an exit animation; onClose fires on animationend, which jsdom
    // never emits on its own, so drive it to completion the way the browser would.
    fireEvent.animationEnd(screen.getByRole("dialog"))
    expect(onClose).toHaveBeenCalled()
  })

  test("switching to Add people fetches candidates and filters existing collaborators out", async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === "/api/organization/members") {
        return Promise.resolve({
          users: [
            { id: "u1", display_name: "Alice", picture: null },
            { id: "u3", display_name: "Carol", picture: null },
            { id: "u9", display_name: "Dana", picture: null },
          ],
        }) as any
      }
      return Promise.reject(new Error(`unexpected ${url}`))
    })
    render(
      <CollaboratorPanel
        collaborators={collaborators}
        currentUserId="u2"
        onClose={vi.fn()}
        onAdd={vi.fn()}
        onLeave={vi.fn(async () => ({}))}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: /Add people/i }))
    // The list view remains mounted behind the slider, so scope queries
    // to the Add view's section (the one containing the add-search input).
    const addSection = (await waitFor(() =>
      screen.getByLabelText("Search people to add").closest("[aria-hidden='false']")
    )) as HTMLElement
    await waitFor(() => expect(within(addSection).getByText("Dana")).toBeTruthy())
    expect(within(addSection).queryByText("Carol")).toBeNull() // already a collaborator
    expect(within(addSection).queryByText("Alice")).toBeNull()
  })

  test("hides Leave button when canLeave is false (DM panel)", () => {
    const dmCollaborators = [
      { id: "m1", user: { id: "u1", display_name: "Alice", picture: null } },
      { id: "m2", user: { id: "u2", display_name: "Me", picture: null } },
    ]
    render(
      <CollaboratorPanel
        collaborators={dmCollaborators}
        currentUserId="u2"
        canLeave={false}
        onClose={vi.fn()}
        onAdd={vi.fn()}
        onLeave={vi.fn(async () => ({}))}
      />
    )
    expect(screen.queryByLabelText("Leave chat")).toBeNull()
    expect(screen.getByText("Me")).toBeTruthy()
    expect(screen.getByText("Alice")).toBeTruthy()
  })

  test("shows Leave button for multi chats (canLeave defaults to true)", () => {
    render(
      <CollaboratorPanel
        collaborators={collaborators}
        currentUserId="u2"
        onClose={vi.fn()}
        onAdd={vi.fn()}
        onLeave={vi.fn(async () => ({}))}
      />
    )
    expect(screen.getByLabelText("Leave chat")).toBeTruthy()
  })

  test("selecting someone in Add view opens the prompt and looks up existing chats", async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === "/api/organization/members") {
        return Promise.resolve({
          users: [{ id: "u9", display_name: "Dana", picture: null }],
        }) as any
      }
      if (url.startsWith("/api/chats/lookup")) {
        return Promise.resolve({ matches: [], match_group: null, next_cursor: null, has_more: false }) as any
      }
      return Promise.reject(new Error(`unexpected ${url}`))
    })
    const onAdd = vi.fn(async () => ({ chatId: "chat-1", added: true }))
    render(
      <CollaboratorPanel
        collaborators={collaborators}
        currentUserId="u2"
        onClose={vi.fn()}
        onAdd={onAdd}
        onLeave={vi.fn(async () => ({}))}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: /Add people/i }))
    const addSection = (await waitFor(() =>
      screen.getByLabelText("Search people to add").closest("[aria-hidden='false']")
    )) as HTMLElement
    await waitFor(() => expect(within(addSection).getByText("Dana")).toBeTruthy())
    fireEvent.click(within(addSection).getByText("Dana"))
    await waitFor(() => expect(screen.getByRole("button", { name: /Give access to history/i })).toBeTruthy())
    fireEvent.click(screen.getByRole("button", { name: /Give access to history/i }))
    await waitFor(() => expect(onAdd).toHaveBeenCalledWith("u9", true))
  })
})
