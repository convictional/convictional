import { cleanup, fireEvent, render, screen, waitFor } from "../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { queryClient } from "~/react/shared/queryClient"
import { showFlash } from "~/shared/flash"
import { OrganizationUpdatesConfiguration } from "~/react/composites/organizationUpdatesConfiguration/OrganizationUpdatesConfiguration"
import type { UpdatesConfiguration } from "~/react/composites/organizationUpdatesConfiguration/types"
import { setCurrentUser } from "../../shared/currentUserFixtures"

const mockedFetch = vi.mocked(apiFetch)
const mockedFlash = vi.mocked(showFlash)
const ENDPOINT = "/api/organization/updates_configuration"

function buildConfig(overrides: Partial<UpdatesConfiguration> = {}): UpdatesConfiguration {
  return {
    frequency: "weekly",
    hour: 9,
    day_of_week: "1",
    goal_update_question: "How's it going?",
    has_goals: true,
    enabled: true,
    ...overrides,
  }
}

async function renderLoaded(config: UpdatesConfiguration) {
  mockedFetch.mockResolvedValueOnce(config)
  render(<OrganizationUpdatesConfiguration />)
  await waitFor(() => expect(mockedFetch).toHaveBeenCalledWith(ENDPOINT))
  await screen.findByLabelText("Frequency")
}

beforeEach(() => {
  mockedFetch.mockReset()
  mockedFlash.mockReset()
  setCurrentUser({ id: "u1", time_zone: "America/New_York" })
})

afterEach(() => {
  cleanup()
  // Reset the shared singleton cache so the updates_configuration query refetches
  // through the mock each test (and the seeded current user is cleared).
  queryClient.clear()
})

describe("OrganizationUpdatesConfiguration", () => {
  test("loads state and renders the schedule fields, badge, and goal question", async () => {
    await renderLoaded(buildConfig())

    expect(screen.getByLabelText("Frequency")).toHaveValue("weekly")
    expect(screen.getByLabelText("Day of week")).toHaveValue("1")
    expect(screen.getByLabelText("Time")).toHaveValue("9")
    expect(screen.getByLabelText("Question")).toHaveValue("How's it going?")
    expect(screen.getByText("Enabled")).toBeInTheDocument()
  })

  test("disabled badge renders when not enabled", async () => {
    await renderLoaded(buildConfig({ enabled: false }))
    expect(screen.getByText("Disabled")).toBeInTheDocument()
  })

  test("toggling weekly↔monthly shows/hides the day-of-week control", async () => {
    await renderLoaded(buildConfig())
    expect(screen.getByLabelText("Day of week")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("Frequency"), { target: { value: "monthly" } })
    expect(screen.queryByLabelText("Day of week")).toBeNull()
    expect(screen.getByText("Updates will be sent on the last day of each month")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("Frequency"), { target: { value: "weekly" } })
    expect(screen.getByLabelText("Day of week")).toBeInTheDocument()
    expect(screen.queryByText("Updates will be sent on the last day of each month")).toBeNull()
  })

  test("saving the schedule PATCHes frequency, hour, and day_of_week as one unit", async () => {
    await renderLoaded(buildConfig())
    mockedFetch.mockResolvedValueOnce(buildConfig({ hour: 14 }))

    fireEvent.change(screen.getByLabelText("Time"), { target: { value: "14" } })
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        ENDPOINT,
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ frequency: "weekly", hour: 14, day_of_week: "1" }),
        })
      )
    })
    await waitFor(() => expect(mockedFlash).toHaveBeenCalledWith("Schedule saved.", "success"))
  })

  test("monthly schedule sends day_of_week as null", async () => {
    await renderLoaded(buildConfig())
    mockedFetch.mockResolvedValueOnce(buildConfig({ frequency: "monthly", day_of_week: null }))

    fireEvent.change(screen.getByLabelText("Frequency"), { target: { value: "monthly" } })
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        ENDPOINT,
        expect.objectContaining({ body: JSON.stringify({ frequency: "monthly", hour: 9, day_of_week: null }) })
      )
    })
  })

  test("a 422 validation error surfaces inline rather than throwing", async () => {
    await renderLoaded(buildConfig())
    mockedFetch.mockRejectedValueOnce(
      new ApiError(422, { detail: "Day of week must be provided and be between 0 (Sunday) and 6 (Saturday)" })
    )

    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Day of week must be provided")
    // A failed save must not claim success.
    expect(mockedFlash).not.toHaveBeenCalledWith("Schedule saved.", "success")
  })

  test("saving the goal question PATCHes goal_update_question", async () => {
    await renderLoaded(buildConfig())
    mockedFetch.mockResolvedValueOnce(buildConfig({ goal_update_question: "What's blocking you?" }))

    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "What's blocking you?" } })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        ENDPOINT,
        expect.objectContaining({ body: JSON.stringify({ goal_update_question: "What's blocking you?" }) })
      )
    })
    await waitFor(() => expect(mockedFlash).toHaveBeenCalledWith("Goal update question saved.", "success"))
  })

  test("saving the question preserves unsaved schedule edits (and vice versa)", async () => {
    await renderLoaded(buildConfig())
    // The question PATCH echoes the server's hour 9 — the old code re-seeded every field
    // from that response and would have reverted the unsaved Time edit below.
    mockedFetch.mockResolvedValueOnce(buildConfig({ goal_update_question: "New question?" }))

    fireEvent.change(screen.getByLabelText("Time"), { target: { value: "14" } })
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "New question?" } })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(2))
    expect(screen.getByLabelText("Time")).toHaveValue("14")
    expect(screen.getByLabelText("Question")).toHaveValue("New question?")
  })

  test("has_goals=false hides the goal-question form", async () => {
    await renderLoaded(buildConfig({ has_goals: false, enabled: false }))

    expect(screen.queryByLabelText("Question")).toBeNull()
    expect(screen.queryByText("Goal update question")).toBeNull()
    // The schedule form still renders.
    expect(screen.getByLabelText("Frequency")).toBeInTheDocument()
  })

  test("renders an error state when the initial load fails", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError(500, null))
    render(<OrganizationUpdatesConfiguration />)

    expect(await screen.findByText("Could not load updates configuration.")).toBeInTheDocument()
  })
})
