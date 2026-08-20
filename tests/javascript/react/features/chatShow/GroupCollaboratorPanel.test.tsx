import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { cleanup, fireEvent, render, screen, waitFor, within } from "../../shared/testUtils"
import { resetOrganizationMembers } from "../../shared/organizationMembersFixtures"

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
import { GroupCollaboratorPanel } from "../../../../../app/javascript/react/features/chatShow/GroupCollaboratorPanel"

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

describe("GroupCollaboratorPanel", () => {
  test("renders collaborators list and close button", () => {
    const onClose = vi.fn()
    render(
      <GroupCollaboratorPanel
        groupId="g1"
        collaborators={collaborators}
        currentUserId="u2"
        onClose={onClose}
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

  test("any collaborator sees Add to group button; only self gets Leave group", () => {
    render(
      <GroupCollaboratorPanel
        groupId="g1"
        collaborators={collaborators}
        currentUserId="u2"
        onClose={vi.fn()}
      />
    )
    expect(screen.getByRole("button", { name: /Add to group/i })).toBeTruthy()
    // Self gets Leave group button
    expect(screen.getByLabelText("Leave group")).toBeTruthy()
    // Others do not get a remove button
    expect(screen.queryByLabelText("Remove Alice from group")).toBeNull()
    expect(screen.queryByLabelText("Remove Carol from group")).toBeNull()
  })

  test("add flow shows confirmation without lookup, calls groups API", async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === "/api/organization/members") {
        return Promise.resolve({
          users: [
            { id: "u1", display_name: "Alice", picture: null },
            { id: "u9", display_name: "Dana", picture: null },
          ],
        }) as any
      }
      if (url === "/api/groups/g1/members") {
        return Promise.resolve({}) as any
      }
      return Promise.reject(new Error(`unexpected ${url}`))
    })

    render(
      <GroupCollaboratorPanel
        groupId="g1"
        collaborators={collaborators}
        currentUserId="u2"
        onClose={vi.fn()}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: /Add to group/i }))

    const addSection = (await waitFor(() =>
      screen.getByLabelText("Search people to add").closest("[aria-hidden='false']")
    )) as HTMLElement

    // Dana is not a current collaborator, so should appear
    await waitFor(() => expect(within(addSection).getByText("Dana")).toBeTruthy())
    // Alice is already a collaborator, should be filtered out
    expect(within(addSection).queryByText("Alice")).toBeNull()

    // No lookup call — groups don't need it
    expect(mockApi).not.toHaveBeenCalledWith(expect.stringContaining("/api/chats/lookup"), expect.anything())

    // Select Dana to see the confirm prompt
    fireEvent.click(within(addSection).getByText("Dana"))
    // Confirm text uses a span for the name, so match the button directly
    await waitFor(() => expect(screen.getByRole("button", { name: /^Add to group$/ })).toBeTruthy())

    // Confirm add
    fireEvent.click(screen.getByRole("button", { name: /Add to group/i, hidden: false }))
    await waitFor(() =>
      expect(mockApi).toHaveBeenCalledWith(
        "/api/groups/g1/members",
        expect.objectContaining({ method: "POST" })
      )
    )
  })
})
