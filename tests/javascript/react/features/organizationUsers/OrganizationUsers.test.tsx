import { act, cleanup, fireEvent, render, screen, waitFor, within } from "../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

// The live-update channel isn't under test here; mocking it keeps the hook off
// the channels client (absent in jsdom), which would otherwise warn.
vi.mock("~/react/shared/hooks/useChannel", () => ({ useChannel: vi.fn() }))

// Auto-confirm the deactivate dialog so the PATCH fires without a mounted
// ConfirmationDialog island.
vi.mock("~/react/composites/confirmationDialog/confirm", () => ({ confirm: vi.fn(async () => true) }))

import { apiFetch } from "~/react/shared/apiFetch"
import { OrganizationUsers } from "~/react/features/organizationUsers/OrganizationUsers"
import type { OrganizationUser, OrganizationUsersListResponse } from "~/react/features/organizationUsers/types"
import { showFlash } from "~/shared/flash"

import { buildCurrentUserApiResponse, resetCurrentUser, setCurrentUser } from "../../shared/currentUserFixtures"

const mockedFetch = vi.mocked(apiFetch)
const mockedFlash = vi.mocked(showFlash)

const CURRENT_USER_ID = "user-me"

function makeUser(overrides: Partial<OrganizationUser> = {}): OrganizationUser {
  return {
    id: "user-1",
    display_name: "Alice Adams",
    picture: null,
    email: "alice@example.com",
    bio: null,
    is_admin: false,
    active: true,
    groups: [],
    ...overrides,
  }
}

const ME = makeUser({ id: CURRENT_USER_ID, display_name: "Me", email: "me@example.com", is_admin: true })

// The raw /api/users/me payload useCurrentUser splits into { user, clientConfig }.
const ME_API_RESPONSE = buildCurrentUserApiResponse({ id: CURRENT_USER_ID, display_name: "Me", is_admin: true })
const ALICE = makeUser({ id: "user-1", display_name: "Alice Adams", email: "alice@example.com" })
const BOB = makeUser({ id: "user-2", display_name: "Bob Brown", email: "bob@example.com", active: false })

function routeFetch(users: OrganizationUser[] = [ME, ALICE, BOB]) {
  const list: OrganizationUsersListResponse = {
    users,
    next_cursor: null,
    has_more: false,
  }
  mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET"
    const body = init?.body ? JSON.parse(init.body as string) : {}
    if (url === "/api/organization/users" && method === "GET") return list
    if (url === "/api/organization/users" && method === "POST") return makeUser({ id: "user-new", email: body.email })
    if (url.startsWith("/api/organization/users/") && method === "PATCH") {
      // Echo the PATCH body onto the targeted member, mirroring the real endpoint
      // returning the updated OrganizationUserResponse.
      const id = url.split("/").pop()
      const target = users.find(u => u.id === id) ?? ALICE
      return { ...target, ...body }
    }
    throw new Error(`unexpected fetch: ${method} ${url}`)
  })
}

beforeEach(() => {
  mockedFetch.mockReset()
  mockedFlash.mockReset()
  setCurrentUser({ id: CURRENT_USER_ID, display_name: "Me", email: "me@example.com" })
})

afterEach(() => {
  cleanup()
  resetCurrentUser()
})

describe("OrganizationUsers", () => {
  test("renders active members, and the deactivated tab shows deactivated members", async () => {
    routeFetch()
    render(<OrganizationUsers />)

    // Active tab (default): the active members render, the deactivated one does not.
    expect(await screen.findByText("Alice Adams")).toBeInTheDocument()
    expect(screen.getByText("Me")).toBeInTheDocument()
    expect(screen.queryByText("Bob Brown")).toBeNull()
    expect(screen.getByRole("tab", { name: "Active Members", selected: true })).toBeInTheDocument()

    fireEvent.click(screen.getByText("Deleted Members"))
    expect(await screen.findByText("Bob Brown")).toBeInTheDocument()
    expect(screen.queryByText("Alice Adams")).toBeNull()
    expect(screen.getByRole("tab", { name: "Deleted Members", selected: true })).toBeInTheDocument()
  })

  test("inviting POSTs email + note to the users endpoint", async () => {
    routeFetch()
    render(<OrganizationUsers />)

    const emailInput = await screen.findByPlaceholderText("Type their email...")
    fireEvent.change(emailInput, { target: { value: "new@example.com" } })
    fireEvent.change(screen.getByPlaceholderText(/personal note/), { target: { value: "Welcome!" } })
    fireEvent.click(screen.getByRole("button", { name: "Invite" }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/organization/users",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ email: "new@example.com", note: "Welcome!" }),
        }),
        expect.anything()
      )
    })
    await waitFor(() => expect(mockedFlash).toHaveBeenCalledWith("Invite sent.", "success"))
  })

  const listGets = () =>
    mockedFetch.mock.calls.filter(
      ([url, init]) => url === "/api/organization/users" && (init?.method ?? "GET") === "GET"
    ).length

  test("promoting PATCHes is_admin: true and applies the result locally without refetching", async () => {
    routeFetch()
    const { container } = render(<OrganizationUsers />)

    const aliceRow = (await screen.findByText("Alice Adams")).closest("#user-row-user-1") as HTMLElement
    fireEvent.click(within(aliceRow).getByRole("button", { name: "Make this user an admin" }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/organization/users/user-1",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ is_admin: true }) })
      )
    })
    // The PATCH response is upserted locally: Alice's row gains the admin shield and
    // the button flips to "Remove admin privileges" — all without a list refetch.
    const updatedRow = container.querySelector("#user-row-user-1") as HTMLElement
    await waitFor(() =>
      expect(within(updatedRow).getByRole("button", { name: "Remove admin privileges" })).toBeInTheDocument()
    )
    expect(listGets()).toBe(1)
  })

  test("deactivating PATCHes active: false, moving the member to the Deleted tab without refetching", async () => {
    routeFetch()
    render(<OrganizationUsers />)

    const aliceRow = (await screen.findByText("Alice Adams")).closest("#user-row-user-1") as HTMLElement
    fireEvent.click(within(aliceRow).getByRole("button", { name: "Remove user from organization" }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/organization/users/user-1",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ active: false }) })
      )
    })
    // Local upsert flips Alice to inactive: she drops off the Active tab and
    // appears under Deleted — no second GET.
    await waitFor(() => expect(screen.queryByText("Alice Adams")).toBeNull())
    fireEvent.click(screen.getByText("Deleted Members"))
    expect(await screen.findByText("Alice Adams")).toBeInTheDocument()
    expect(listGets()).toBe(1)
  })

  test("waits for the current user to resolve before rendering rows", async () => {
    // Identity unresolved (cold load): hold /api/users/me in flight while the
    // member list resolves, so useCurrentUser stays loading with no user.
    resetCurrentUser()
    let resolveMe!: (value: unknown) => void
    const mePromise = new Promise(resolve => {
      resolveMe = resolve
    })
    const list: OrganizationUsersListResponse = {
      users: [ME, ALICE, BOB],
      channel_topic_id: "signed-org-members-topic",
      next_cursor: null,
      has_more: false,
    }
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/api/users/me") return mePromise
      if (url === "/api/organization/users" && (init?.method ?? "GET") === "GET") return list
      throw new Error(`unexpected fetch: ${url}`)
    })
    render(<OrganizationUsers />)

    // Even after the member list GET resolves, no rows render while identity is unknown,
    // so the admin's own row can't briefly expose self-actions.
    await waitFor(() => expect(listGets()).toBe(1))
    expect(screen.queryByText("Alice Adams")).toBeNull()

    // Once identity resolves, the list renders.
    await act(async () => {
      resolveMe(ME_API_RESPONSE)
    })
    expect(await screen.findByText("Alice Adams")).toBeInTheDocument()
  })

  test("hides actions on the current user's own row", async () => {
    routeFetch()
    render(<OrganizationUsers />)

    const myRow = (await screen.findByText("Me")).closest("#user-row-user-me") as HTMLElement
    expect(within(myRow).getByText("(you)")).toBeInTheDocument()
    expect(within(myRow).queryByRole("button", { name: "Remove user from organization" })).toBeNull()
    expect(within(myRow).queryByRole("button", { name: "Remove admin privileges" })).toBeNull()
  })

  test("renders read-only (no self-mutation actions) when the current user fails to load", async () => {
    // /api/users/me errored: identity is resolved-but-unknown. The list still renders,
    // but with currentUserId null no row may expose actions the server would 422.
    resetCurrentUser()
    const list: OrganizationUsersListResponse = {
      users: [ME, ALICE, BOB],
      channel_topic_id: "signed-org-members-topic",
      next_cursor: null,
      has_more: false,
    }
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/api/users/me") throw new Error("boom")
      if (url === "/api/organization/users" && (init?.method ?? "GET") === "GET") return list
      throw new Error(`unexpected fetch: ${url}`)
    })
    render(<OrganizationUsers />)

    expect(await screen.findByText("Alice Adams")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Make this user an admin" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Remove user from organization" })).toBeNull()
  })

})
