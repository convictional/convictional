import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { Notifications } from "../../../../../app/javascript/react/features/notifications/Notifications"
import type {
  NotificationPreference,
  NotificationsResponse,
  PostGroupMute,
} from "../../../../../app/javascript/react/features/notifications/types"

const apiFetchMock = vi.fn()

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
  errorMessage: (err: unknown, fallback: string) =>
    err instanceof Error && err.message ? err.message : fallback,
  ApiError: class extends Error {},
}))

function makePreference(overrides: Partial<NotificationPreference> = {}): NotificationPreference {
  return {
    resource_type: "Goal",
    default_level: "all",
    ...overrides,
  }
}

function makeResponse(
  preferences: NotificationPreference[] = [],
  postGroupMutes: PostGroupMute[] = [],
): NotificationsResponse {
  return {
    preferences,
    post_group_mutes: postGroupMutes,
    push: { devices: [], vapid_public_key: "" },
  }
}

describe("Notifications", () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(cleanup)

  test("fetches preferences on mount and renders a row per source", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeResponse([
        makePreference({ resource_type: "Post" }),
        makePreference({ resource_type: "Goal" }),
      ]),
    )

    render(<Notifications />)

    await waitFor(() => {
      expect(screen.getByText("Posts")).toBeInTheDocument()
    })
    expect(screen.getByText("Goals")).toBeInTheDocument()
    expect(screen.getByText(/direct asks always reach you/i)).toBeInTheDocument()
  })

  test("clicking a radio saves immediately with no modal", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeResponse([makePreference({ resource_type: "Goal" })]),
    )
    apiFetchMock.mockResolvedValueOnce(
      makePreference({ resource_type: "Goal", default_level: "relevant_only" }),
    )

    render(<Notifications />)
    await waitFor(() => screen.getByText("Goals"))

    fireEvent.click(screen.getByRole("radio", { name: /relevant to me/i }))

    // No modal — settings are forward-looking by design; the radio just sets policy.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    await waitFor(() => {
      const patchCall = apiFetchMock.mock.calls.find(call => call[0] === "/api/notifications/goal")
      expect(patchCall?.[1]).toMatchObject({ method: "PATCH" })
      const body = JSON.parse(patchCall?.[1]?.body as string)
      expect(body).toEqual({ default_level: "relevant_only" })
    })
  })

  test("Posts with an existing mute auto-expands the Groups panel", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeResponse(
        [makePreference({ resource_type: "Post" })],
        [
          { group_id: "g-1", group_name: "Marketing", muted: false },
          { group_id: "g-2", group_name: "Engineering", muted: true },
        ],
      ),
    )
    apiFetchMock.mockResolvedValueOnce({
      group_id: "g-1",
      group_name: "Marketing",
      muted: true,
    })

    render(<Notifications />)
    await waitFor(() => screen.getByText("Posts"))

    // Panel is visible because at least one group is muted.
    expect(screen.getByText("Marketing")).toBeInTheDocument()
    expect(screen.getByText("Engineering")).toBeInTheDocument()

    // Toggle Marketing off (mute) — Marketing's row uses checked=!muted, so clicking unchecks the toggle.
    const marketingToggle = screen.getByRole("checkbox", { name: /mute Marketing/i })
    fireEvent.click(marketingToggle)

    await waitFor(() => {
      const patchCall = apiFetchMock.mock.calls.find(
        call => call[0] === "/api/notifications/posts/groups/g-1/mute",
      )
      expect(patchCall?.[1]).toMatchObject({ method: "PATCH" })
      const body = JSON.parse(patchCall?.[1]?.body as string)
      expect(body).toEqual({ muted: true })
    })
  })

  test("Groups panel starts collapsed when no group is muted", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeResponse(
        [makePreference({ resource_type: "Post" })],
        [{ group_id: "g-1", group_name: "Marketing", muted: false }],
      ),
    )

    render(<Notifications />)
    await waitFor(() => screen.getByText("Posts"))

    expect(screen.queryByText("Marketing")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /groups you're in/i }))
    expect(screen.getByText("Marketing")).toBeInTheDocument()
  })

  test("Unmuting a group sends muted=false to the mute endpoint", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeResponse(
        [makePreference({ resource_type: "Post" })],
        [{ group_id: "g-1", group_name: "Marketing", muted: true }],
      ),
    )
    apiFetchMock.mockResolvedValueOnce({
      group_id: "g-1",
      group_name: "Marketing",
      muted: false,
    })

    render(<Notifications />)
    await waitFor(() => screen.getByText("Posts"))

    // Marketing is currently muted; the toggle is rendered with checked=!muted, so it's unchecked.
    // Clicking it (checking the toggle) flips the row to unmuted.
    const marketingToggle = screen.getByRole("checkbox", { name: /unmute Marketing/i })
    fireEvent.click(marketingToggle)

    await waitFor(() => {
      const patchCall = apiFetchMock.mock.calls.find(
        call => call[0] === "/api/notifications/posts/groups/g-1/mute",
      )
      const body = JSON.parse(patchCall?.[1]?.body as string)
      expect(body).toEqual({ muted: false })
    })
  })

  test("Posts row renders three radios; clicking broadcasts PATCHes that level", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeResponse([
        makePreference({ resource_type: "Post", default_level: "broadcasts" }),
        makePreference({ resource_type: "Goal", default_level: "relevant_only" }),
      ]),
    )
    apiFetchMock.mockResolvedValueOnce(makePreference({ resource_type: "Post", default_level: "all" }))

    render(<Notifications />)
    await waitFor(() => screen.getByText("Posts"))

    // Posts has three radios; Goal still has two.
    expect(screen.getAllByRole("radio", { name: /everyone and my groups/i })).toHaveLength(1)
    expect(screen.getAllByRole("radio").filter(r => r.getAttribute("name") === "level-Post")).toHaveLength(3)
    expect(screen.getAllByRole("radio").filter(r => r.getAttribute("name") === "level-Goal")).toHaveLength(2)

    // Flip Posts to All — PATCH /api/notifications/post with default_level=all.
    const postsAll = screen
      .getAllByRole("radio", { name: /^All/i })
      .find(r => r.getAttribute("name") === "level-Post")
    fireEvent.click(postsAll!)

    await waitFor(() => {
      const patchCall = apiFetchMock.mock.calls.find(call => call[0] === "/api/notifications/post")
      expect(patchCall?.[1]).toMatchObject({ method: "PATCH" })
      expect(JSON.parse(patchCall?.[1]?.body as string)).toEqual({ default_level: "all" })
    })
  })

  test("error during fetch renders ErrorState", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("boom"))

    render(<Notifications />)

    await waitFor(() => {
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
    })
  })
})
