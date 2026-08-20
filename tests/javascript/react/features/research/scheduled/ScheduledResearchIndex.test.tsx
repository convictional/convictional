import { cleanup, fireEvent, render, screen, waitFor } from "../../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    body: null
    constructor(status: number) {
      super(`Request failed with status ${status}`)
      this.status = status
      this.body = null
    }
  },
}))

vi.mock("~/react/shared/hooks/useChannel", () => ({
  useChannel: vi.fn(),
}))

vi.mock("~/channels/client", () => ({
  getChannelsClient: vi.fn(() => null),
}))

vi.mock("~/shared/flash", () => ({
  showFlash: vi.fn(),
}))

import { apiFetch } from "~/react/shared/apiFetch"
import {
  OPEN_EVENT as RESEARCH_DIALOG_OPEN_EVENT,
  SCHEDULED_RESEARCH_CHANGED_EVENT,
} from "~/react/features/research/dialog/hooks/useResearchDialog"
import { ScheduledResearchIndex } from "~/react/features/research/scheduled/ScheduledResearchIndex"
import {
  ScheduledResearchFrequency,
  type ScheduledResearch,
  type ScheduledResearchListResponse,
} from "~/react/features/research/scheduled/types"
import { resetCurrentUser, setCurrentUser } from "../../../shared/currentUserFixtures"

const mockApiFetch = vi.mocked(apiFetch)

function makeSchedule(overrides: Partial<ScheduledResearch> = {}): ScheduledResearch {
  return {
    id: "sched-1",
    title: "Weekly ops digest",
    prompt: "What happened in ops this week?",
    frequency: ScheduledResearchFrequency.WEEKLY,
    hour: 9,
    day_of_week: "1",
    schedule_description: "Weekly on Monday at 09:00",
    next_run_at: "2026-05-01T09:00:00Z",
    last_delivered_at: "2026-04-24T09:00:00Z",
    preparation_failed_at: null,
    created_at: "2026-04-17T09:00:00Z",
    ...overrides,
  }
}

function makeListResponse(overrides: Partial<ScheduledResearchListResponse> = {}): ScheduledResearchListResponse {
  return {
    scheduled_researches: [makeSchedule()],
    next_cursor: null,
    has_more: false,
    ...overrides,
  }
}

beforeEach(() => {
  window.history.replaceState(null, "", "/scheduled_research")
  setCurrentUser({ id: "u1", time_zone: "America/New_York" })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  resetCurrentUser()
})

describe("ScheduledResearchIndex", () => {
  test("renders the list after a successful fetch", async () => {
    mockApiFetch.mockResolvedValueOnce(makeListResponse())

    render(<ScheduledResearchIndex />)

    expect(mockApiFetch).toHaveBeenCalledWith(
      "/api/scheduled_research",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(await screen.findByText("Weekly ops digest")).toBeInTheDocument()
  })

  test("renders the empty state when there are no schedules", async () => {
    mockApiFetch.mockResolvedValueOnce(makeListResponse({ scheduled_researches: [] }))

    render(<ScheduledResearchIndex />)

    expect(await screen.findByTestId("scheduled-research-empty")).toBeInTheDocument()
  })

  test("clicking an empty-state example dispatches open with the prefilled prompt", async () => {
    mockApiFetch.mockResolvedValueOnce(makeListResponse({ scheduled_researches: [] }))
    const listener = vi.fn()
    window.addEventListener(RESEARCH_DIALOG_OPEN_EVENT, listener)

    render(<ScheduledResearchIndex />)

    const example = await screen.findByText("Catch me up on last week")
    fireEvent.click(example)

    expect(listener).toHaveBeenCalledTimes(1)
    const detail = (listener.mock.calls[0][0] as CustomEvent).detail
    expect(detail).toEqual({
      mode: "schedule",
      prefill: { prompt: "Catch me up on work from last week. Use bullet points, no more than 10." },
    })

    window.removeEventListener(RESEARCH_DIALOG_OPEN_EVENT, listener)
  })

  test("clicking the + button dispatches research-dialog:open in schedule mode", async () => {
    mockApiFetch.mockResolvedValueOnce(makeListResponse({ scheduled_researches: [] }))
    const listener = vi.fn()
    window.addEventListener(RESEARCH_DIALOG_OPEN_EVENT, listener)

    render(<ScheduledResearchIndex />)

    const newButton = await screen.findByTestId("scheduled-research-new-button")
    fireEvent.click(newButton)

    expect(listener).toHaveBeenCalledTimes(1)
    const detail = (listener.mock.calls[0][0] as CustomEvent).detail
    expect(detail).toEqual({ mode: "schedule" })

    window.removeEventListener(RESEARCH_DIALOG_OPEN_EVENT, listener)
  })

  test("?prefill_from= fetches the prefill and dispatches the open event with it", async () => {
    window.history.replaceState(null, "", "/scheduled_research?prefill_from=question-42")
    mockApiFetch
      .mockResolvedValueOnce(makeListResponse({ scheduled_researches: [] }))
      .mockResolvedValueOnce({ prompt: "Weekly status" })

    const listener = vi.fn()
    window.addEventListener(RESEARCH_DIALOG_OPEN_EVENT, listener)

    render(<ScheduledResearchIndex />)

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/api/scheduled_research/prefill?from_research_question=question-42")
    })
    await waitFor(() => {
      expect(listener).toHaveBeenCalledTimes(1)
    })
    const detail = (listener.mock.calls[0][0] as CustomEvent).detail
    expect(detail).toEqual({ mode: "schedule", prefill: { prompt: "Weekly status" } })
    // URL is cleaned up so a refresh doesn't re-trigger the fetch.
    expect(window.location.search).toBe("")

    window.removeEventListener(RESEARCH_DIALOG_OPEN_EVENT, listener)
  })

  test("displays preparation_failed_at as a 'Preparation failed' badge", async () => {
    mockApiFetch.mockResolvedValueOnce(
      makeListResponse({
        scheduled_researches: [
          makeSchedule({
            title: "Untitled",
            preparation_failed_at: "2026-04-20T09:00:00Z",
          }),
        ],
      })
    )

    render(<ScheduledResearchIndex />)

    expect(await screen.findByTestId("scheduled-research-row-failed")).toHaveTextContent("preparation failed")
    // When preparation failed we don't also show the "title in progress…" pulse.
    expect(screen.queryByTestId("scheduled-research-row-preparing")).toBeNull()
  })

  test("row shows both last-delivered and next-run when both are known", async () => {
    mockApiFetch.mockResolvedValueOnce(
      makeListResponse({
        scheduled_researches: [makeSchedule({ last_delivered_at: "2026-04-24T09:00:00Z" })],
      })
    )

    render(<ScheduledResearchIndex />)

    const row = await screen.findByTestId("scheduled-research-row")
    expect(row).toHaveTextContent(/delivered/)
    // next_run_at is 2026-05-01 → "Fri, May 1".
    expect(row).toHaveTextContent(/May 1/)
  })

  test("row shows only next-run when the schedule has never delivered", async () => {
    mockApiFetch.mockResolvedValueOnce(
      makeListResponse({
        scheduled_researches: [makeSchedule({ last_delivered_at: null })],
      })
    )

    render(<ScheduledResearchIndex />)

    const row = await screen.findByTestId("scheduled-research-row")
    expect(row).not.toHaveTextContent(/delivered/)
    expect(row).toHaveTextContent(/May 1/)
  })

  test("shows 'Title in progress…' for an unprepared untitled row", async () => {
    mockApiFetch.mockResolvedValueOnce(
      makeListResponse({
        scheduled_researches: [makeSchedule({ title: "Untitled", preparation_failed_at: null })],
      })
    )

    render(<ScheduledResearchIndex />)

    expect(await screen.findByTestId("scheduled-research-row-preparing")).toBeInTheDocument()
  })

  test("clicking a row dispatches research-dialog:open with the schedule", async () => {
    const schedule = makeSchedule({ id: "sched-7" })
    mockApiFetch.mockResolvedValueOnce(makeListResponse({ scheduled_researches: [schedule] }))
    const listener = vi.fn()
    window.addEventListener(RESEARCH_DIALOG_OPEN_EVENT, listener)

    render(<ScheduledResearchIndex />)

    const row = await screen.findByTestId("scheduled-research-row")
    fireEvent.click(row)

    expect(listener).toHaveBeenCalledTimes(1)
    const detail = (listener.mock.calls[0][0] as CustomEvent).detail
    expect(detail).toEqual({ mode: "schedule", schedule })

    window.removeEventListener(RESEARCH_DIALOG_OPEN_EVENT, listener)
  })

  test("scheduled-research:changed / updated patches the row in place", async () => {
    const schedule = makeSchedule({ id: "sched-7", title: "Old title" })
    mockApiFetch.mockResolvedValueOnce(makeListResponse({ scheduled_researches: [schedule] }))

    render(<ScheduledResearchIndex />)
    expect(await screen.findByText("Old title")).toBeInTheDocument()

    window.dispatchEvent(
      new CustomEvent(SCHEDULED_RESEARCH_CHANGED_EVENT, {
        detail: { action: "updated", item: { ...schedule, title: "New title" } },
      })
    )

    expect(await screen.findByText("New title")).toBeInTheDocument()
    expect(screen.queryByText("Old title")).toBeNull()
  })

  test("scheduled-research:changed / deleted removes the row", async () => {
    const schedule = makeSchedule({ id: "sched-7" })
    mockApiFetch.mockResolvedValueOnce(makeListResponse({ scheduled_researches: [schedule] }))

    render(<ScheduledResearchIndex />)
    expect(await screen.findByText("Weekly ops digest")).toBeInTheDocument()

    window.dispatchEvent(
      new CustomEvent(SCHEDULED_RESEARCH_CHANGED_EVENT, {
        detail: { action: "deleted", id: "sched-7" },
      })
    )

    await waitFor(() => {
      expect(screen.queryByText("Weekly ops digest")).toBeNull()
    })
    expect(await screen.findByTestId("scheduled-research-empty")).toBeInTheDocument()
  })

  test("scheduled-research:changed / created prepends a new row", async () => {
    mockApiFetch.mockResolvedValueOnce(makeListResponse({ scheduled_researches: [] }))

    render(<ScheduledResearchIndex />)
    expect(await screen.findByTestId("scheduled-research-empty")).toBeInTheDocument()

    const fresh = makeSchedule({ id: "sched-new", title: "Fresh schedule" })
    window.dispatchEvent(
      new CustomEvent(SCHEDULED_RESEARCH_CHANGED_EVENT, {
        detail: { action: "created", item: fresh },
      })
    )

    expect(await screen.findByText("Fresh schedule")).toBeInTheDocument()
  })

  test("hash #<id> opens the dialog for the matching schedule and clears the hash", async () => {
    const schedule = makeSchedule({ id: "sched-9" })
    window.history.replaceState(null, "", "/scheduled_research#sched-9")
    mockApiFetch.mockResolvedValueOnce(makeListResponse({ scheduled_researches: [schedule] }))

    const listener = vi.fn()
    window.addEventListener(RESEARCH_DIALOG_OPEN_EVENT, listener)

    render(<ScheduledResearchIndex />)

    await waitFor(() => {
      expect(listener).toHaveBeenCalledTimes(1)
    })
    const detail = (listener.mock.calls[0][0] as CustomEvent).detail
    expect(detail).toEqual({ mode: "schedule", schedule })
    expect(window.location.hash).toBe("")

    window.removeEventListener(RESEARCH_DIALOG_OPEN_EVENT, listener)
  })
})
