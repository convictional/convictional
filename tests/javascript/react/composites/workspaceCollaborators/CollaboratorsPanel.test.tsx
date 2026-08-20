import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { cleanup, render, screen, within } from "../../shared/testUtils"
import { resetOrganizationMembers, setOrganizationMembers } from "../../shared/organizationMembersFixtures"

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
import { CollaboratorsPanel } from "../../../../../app/javascript/react/composites/workspaceCollaborators/components/CollaboratorsPanel"
import type { WorkspaceCollaboratorsData } from "../../../../../app/javascript/react/shared/types"

const mockApi = vi.mocked(apiFetch)

const orgUsers = [
  { id: "u1", display_name: "Alice", picture: null },
  { id: "u2", display_name: "Bob", picture: null },
  { id: "u3", display_name: "Carol", picture: null },
]

const unviewed = { viewed: false, last_viewed_at: null, last_viewed_event_id: null }

function buildData(): WorkspaceCollaboratorsData {
  return {
    collaborators: [
      {
        id: "c1",
        user: { id: "u1", display_name: "Alice", picture: null },
        is_removable: true,
        status: "approved",
        view_state: unviewed,
      },
    ],
    pending: [
      {
        id: "c2",
        user: { id: "u2", display_name: "Bob", picture: null },
        is_removable: true,
        status: "pending",
        view_state: unviewed,
      },
    ],
    viewers: [],
    present_user_ids: [],
    current_user_view_state: unviewed,
  }
}

beforeEach(() => {
  // Seed the shared cache directly so the panel renders synchronously without
  // depending on the fetch lifecycle.
  setOrganizationMembers({ users: orgUsers as never })
  mockApi.mockResolvedValue({ users: orgUsers, groups: [] } as never)
})

afterEach(() => {
  cleanup()
  mockApi.mockReset()
  resetOrganizationMembers()
})

describe("CollaboratorsPanel", () => {
  test("pending access-requesters remain addable in 'Everyone else'", () => {
    render(
      <CollaboratorsPanel
        data={buildData()}
        currentUserId="u1"
        onAdd={vi.fn(async () => {})}
        onRemove={vi.fn(async () => {})}
        onInvite={vi.fn(async () => {})}
        onApprove={vi.fn(async () => {})}
      />
    )

    // The component tags add rows with `data-test-id` (hyphenated), not the
    // Testing Library default `data-testid`.
    const addRow = (userId: string) => document.querySelector(`[data-test-id="add-collaborator-${userId}"]`)
    // Approved collaborator (Alice) is excluded from "Everyone else"...
    expect(addRow("u1")).toBeNull()
    // ...but the pending requester (Bob) stays listed so an admin can add them
    // directly, matching the pre-store behaviour. Carol (uninvolved) is listed too.
    expect(addRow("u2")).toBeTruthy()
    expect(addRow("u3")).toBeTruthy()
    // Bob still also appears under "Requested Access".
    expect(screen.getByLabelText("Approve Bob")).toBeTruthy()
  })

  test("hides the current user's own view-state indicator but keeps others'", () => {
    const data = buildData()
    data.collaborators.push({
      id: "c3",
      user: { id: "u3", display_name: "Carol", picture: null },
      is_removable: true,
      status: "approved",
      view_state: unviewed,
    })

    render(
      <CollaboratorsPanel
        data={data}
        currentUserId="u1"
        onAdd={vi.fn(async () => {})}
        onRemove={vi.fn(async () => {})}
        onInvite={vi.fn(async () => {})}
        onApprove={vi.fn(async () => {})}
      />
    )

    // Own view state is unreliable (records on load) and redundant, so Alice (u1, the current user)
    // shows no indicator; only Carol (u3) does. Pending rows never render one.
    const indicators = document.querySelectorAll('[data-test-id="collaborator-view-state"]')
    expect(indicators.length).toBe(1)
  })
})
