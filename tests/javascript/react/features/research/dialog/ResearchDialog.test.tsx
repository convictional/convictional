import { act, cleanup, fireEvent, render, screen, waitFor } from "../../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => {
  class ApiError extends Error {
    status: number
    body: { detail?: string } | null
    constructor(status: number, body: { detail?: string } | null = null) {
      const detail = body?.detail
      const message = (typeof detail === "string" ? detail : null) || `Request failed with status ${status}`
      super(message)
      this.status = status
      this.body = body
    }
  }
  return {
    apiFetch: vi.fn(),
    ApiError,
    errorMessage: (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback),
  }
})

const confirmMock = vi.fn(() => Promise.resolve(true))
vi.mock("~/react/composites/confirmationDialog/confirm", () => ({
  confirm: (...args: unknown[]) => confirmMock(...args),
}))

// These tests don't exercise channel-backed live updates, so there's no client
// registered; mock the hook to the same null it would resolve to, minus the
// "not available at mount" warning it logs for a genuinely clientless mount.
vi.mock("~/react/shared/hooks/useChannelsClient", () => ({
  useChannelsClient: () => null,
}))

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { ResearchDialog } from "~/react/features/research/dialog/ResearchDialog"
import {
  CLOSED_EVENT,
  OPEN_EVENT,
  SCHEDULED_RESEARCH_CHANGED_EVENT,
  type ResearchDialogMode,
  type ScheduledResearchChangedDetail,
} from "~/react/features/research/dialog/hooks/useResearchDialog"
import { ScheduledResearchFrequency, type ScheduledResearch } from "~/react/features/research/scheduled/types"
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
    last_delivered_at: null,
    preparation_failed_at: null,
    created_at: "2026-04-17T09:00:00Z",
    ...overrides,
  }
}

function dispatchOpen(detail?: {
  mode?: ResearchDialogMode
  prefill?: { prompt?: string }
  schedule?: ScheduledResearch
}) {
  act(() => {
    window.dispatchEvent(new CustomEvent(OPEN_EVENT, detail ? { detail } : undefined))
  })
}

function setPathname(pathname: string) {
  Object.defineProperty(window, "location", {
    value: { reload: vi.fn(), assign: vi.fn(), pathname },
    writable: true,
    configurable: true,
  })
}

beforeEach(() => {
  mockApiFetch.mockReset()
  confirmMock.mockReset()
  confirmMock.mockResolvedValue(true)
  setPathname("/inbox")
  // Seed "ready" so useCurrentUser doesn't fire a /api/users/me fetch against the mock.
  setCurrentUser({ id: "u1", time_zone: "America/New_York" })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  resetCurrentUser()
  document.documentElement.style.overflow = ""
})

describe("ResearchDialog", () => {
  test("is closed by default", () => {
    render(<ResearchDialog />)
    expect(screen.queryByTestId("research-dialog-form")).toBeNull()
  })

  test("is rendered with role=dialog and aria-modal", () => {
    render(<ResearchDialog />)
    dispatchOpen()

    const dialog = screen.getByRole("dialog")
    expect(dialog.getAttribute("aria-modal")).toBe("true")
    expect(dialog.getAttribute("aria-label")).toBe("Research")
  })

  test("preserves typed body across close and reopen", () => {
    render(<ResearchDialog />)
    dispatchOpen()

    const textarea = screen.getByPlaceholderText("What would you like to research?") as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: "unfinished thought" } })

    fireEvent.keyDown(screen.getByTestId("research-dialog-form"), { key: "Escape" })
    dispatchOpen()

    const reopened = screen.getByPlaceholderText("What would you like to research?") as HTMLTextAreaElement
    expect(reopened.value).toBe("unfinished thought")
  })

  test("opens on research-dialog:open event and focuses the textarea", () => {
    render(<ResearchDialog />)
    dispatchOpen()

    const textarea = screen.getByPlaceholderText("What would you like to research?")
    expect(textarea).toBeTruthy()
    expect(document.activeElement).toBe(textarea)
  })

  test("locks page scroll via the shared lock, not a conflicting body pin", () => {
    render(<ResearchDialog />)
    dispatchOpen()
    expect(document.documentElement.style.overflow).toBe("hidden")
    // A re-pinned body (position:fixed) ignores the scroll-lock padding and shifts the page.
    expect(document.body.style.position).not.toBe("fixed")

    fireEvent.keyDown(screen.getByTestId("research-dialog-form"), { key: "Escape" })

    expect(document.documentElement.style.overflow).not.toBe("hidden")
  })

  test("closes on Escape and dispatches closed event", () => {
    const closed = vi.fn()
    window.addEventListener(CLOSED_EVENT, closed)
    render(<ResearchDialog />)
    dispatchOpen()

    fireEvent.keyDown(screen.getByTestId("research-dialog-form"), { key: "Escape" })

    expect(screen.queryByTestId("research-dialog-form")).toBeNull()
    expect(closed).toHaveBeenCalledTimes(1)
    window.removeEventListener(CLOSED_EVENT, closed)
  })

  test("closes on backdrop click", () => {
    const { container } = render(<ResearchDialog />)
    dispatchOpen()

    const backdrop = document.querySelector('[aria-hidden="true"]') as HTMLElement
    fireEvent.click(backdrop)

    expect(screen.queryByTestId("research-dialog-form")).toBeNull()
    expect(container).toBeTruthy()
  })

  test("preset prompt buttons populate the textarea and refocus", () => {
    render(<ResearchDialog />)
    dispatchOpen()

    fireEvent.click(screen.getByText("Catch me up on last week"))

    const textarea = screen.getByPlaceholderText("What would you like to research?") as HTMLTextAreaElement
    expect(textarea.value).toBe("Catch me up on work from last week. Use bullet points, no more than 10.")
    expect(document.activeElement).toBe(textarea)
  })

  test("submit is disabled when body is empty", () => {
    render(<ResearchDialog />)
    dispatchOpen()

    const submit = screen.getByLabelText("Submit research") as HTMLButtonElement
    expect(submit.disabled).toBe(true)
  })

  test("submits with trimmed body and reloads on success", async () => {
    mockApiFetch.mockResolvedValue({ id: "q1" })
    render(<ResearchDialog />)
    dispatchOpen()

    const textarea = screen.getByPlaceholderText("What would you like to research?") as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: "  research the market  " } })

    fireEvent.click(screen.getByLabelText("Submit research"))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/api/research_questions", {
        method: "POST",
        body: JSON.stringify({ body: "research the market" }),
      })
      expect(window.location.reload).toHaveBeenCalled()
    })
  })

  test("Ctrl+Enter submits the form", async () => {
    mockApiFetch.mockResolvedValue({ id: "q1" })
    render(<ResearchDialog />)
    dispatchOpen()

    const textarea = screen.getByPlaceholderText("What would you like to research?") as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: "quick submit" } })
    fireEvent.keyDown(textarea, { key: "Enter", ctrlKey: true })

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalled()
    })
  })

  test("shows an error message when the submit fails", async () => {
    mockApiFetch.mockRejectedValue(new Error("server exploded"))
    render(<ResearchDialog />)
    dispatchOpen()

    const textarea = screen.getByPlaceholderText("What would you like to research?") as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: "will fail" } })
    fireEvent.click(screen.getByLabelText("Submit research"))

    await waitFor(() => {
      expect(screen.getByText(/something went wrong|server exploded/i)).toBeTruthy()
    })
    // Submit is re-enabled after failure
    expect((screen.getByLabelText("Submit research") as HTMLButtonElement).disabled).toBe(false)
  })

  describe("schedule mode", () => {
    test("opens in schedule mode via event detail and shows schedule fields", () => {
      render(<ResearchDialog />)
      dispatchOpen({ mode: "schedule" })

      expect(screen.getByTestId("scheduled-research-dialog")).toBeInTheDocument()
      expect(screen.getByRole("tab", { name: "Weekly" })).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "Create schedule" })).toBeInTheDocument()
      // Submit-research aria-label is swapped out in schedule mode.
      expect(screen.queryByLabelText("Submit research")).toBeNull()
    })

    test("populates the prompt from prefill detail", () => {
      render(<ResearchDialog />)
      dispatchOpen({ mode: "schedule", prefill: { prompt: "Catch me up" } })

      const textarea = screen.getByPlaceholderText("What would you like to research?") as HTMLTextAreaElement
      expect(textarea.value).toBe("Catch me up")
    })

    test("toggling the Schedule chip reveals and hides the schedule fields", () => {
      render(<ResearchDialog />)
      dispatchOpen()

      const chip = screen.getByTestId("research-dialog-schedule-toggle")
      expect(screen.queryByRole("tab", { name: "Weekly" })).toBeNull()

      fireEvent.click(chip)
      expect(screen.getByRole("tab", { name: "Weekly" })).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "Create schedule" })).toBeInTheDocument()

      fireEvent.click(chip)
      expect(screen.queryByRole("tab", { name: "Weekly" })).toBeNull()
      expect(screen.getByLabelText("Submit research")).toBeInTheDocument()
    })

    test("from off-page: submits to /api/scheduled_research and stays in place (no navigation)", async () => {
      setPathname("/inbox")
      mockApiFetch.mockResolvedValue(makeSchedule())
      render(<ResearchDialog />)
      dispatchOpen({ mode: "schedule" })

      const textarea = screen.getByPlaceholderText("What would you like to research?") as HTMLTextAreaElement
      fireEvent.change(textarea, { target: { value: "  What happened this week?  " } })

      fireEvent.click(screen.getByRole("button", { name: "Create schedule" }))

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith("/api/scheduled_research", {
          method: "POST",
          body: JSON.stringify({
            prompt: "What happened this week?",
            frequency: ScheduledResearchFrequency.WEEKLY,
            hour: 9,
            day_of_week: "1",
          }),
        })
      })
      // Confirmation lives in the flash; we don't yank the user off their current page.
      expect(window.location.assign).not.toHaveBeenCalled()
      await waitFor(() => {
        expect(screen.queryByTestId("research-dialog-form")).toBeNull()
      })
    })

    test("from /scheduled_research: dispatches created event and closes without navigation", async () => {
      setPathname("/scheduled_research")
      const created = makeSchedule({ id: "sched-new", prompt: "New one" })
      mockApiFetch.mockResolvedValue(created)

      const changes: ScheduledResearchChangedDetail[] = []
      const listener = (event: Event) =>
        changes.push((event as CustomEvent<ScheduledResearchChangedDetail>).detail)
      window.addEventListener(SCHEDULED_RESEARCH_CHANGED_EVENT, listener)

      render(<ResearchDialog />)
      dispatchOpen({ mode: "schedule" })

      fireEvent.change(
        screen.getByPlaceholderText("What would you like to research?"),
        { target: { value: "New one" } }
      )
      fireEvent.click(screen.getByRole("button", { name: "Create schedule" }))

      await waitFor(() => {
        expect(changes).toEqual([{ action: "created", item: created }])
      })
      expect(window.location.assign).not.toHaveBeenCalled()
      expect(screen.queryByTestId("research-dialog-form")).toBeNull()

      window.removeEventListener(SCHEDULED_RESEARCH_CHANGED_EVENT, listener)
    })

    test("drops day_of_week when frequency is not WEEKLY", async () => {
      mockApiFetch.mockResolvedValue({ id: "sched-1" })
      render(<ResearchDialog />)
      dispatchOpen({ mode: "schedule" })

      fireEvent.change(
        screen.getByPlaceholderText("What would you like to research?"),
        { target: { value: "Daily digest" } }
      )
      fireEvent.click(screen.getByRole("tab", { name: "Daily" }))
      fireEvent.click(screen.getByRole("button", { name: "Create schedule" }))

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith("/api/scheduled_research", {
          method: "POST",
          body: JSON.stringify({
            prompt: "Daily digest",
            frequency: ScheduledResearchFrequency.DAILY,
            hour: 9,
            day_of_week: null,
          }),
        })
      })
    })

    test("shows a friendly fallback error on submit failure", async () => {
      mockApiFetch.mockRejectedValue(new ApiError(400, { detail: "Hour must be between 0 and 23" }))
      render(<ResearchDialog />)
      dispatchOpen({ mode: "schedule" })

      fireEvent.change(
        screen.getByPlaceholderText("What would you like to research?"),
        { target: { value: "What happened this week?" } }
      )
      fireEvent.click(screen.getByRole("button", { name: "Create schedule" }))

      await waitFor(() => {
        expect(screen.getByTestId("research-dialog-error")).toHaveTextContent("Something went wrong")
      })
      expect((screen.getByRole("button", { name: "Create schedule" }) as HTMLButtonElement).disabled).toBe(false)
    })

    test("Preview button is disabled until there's a prompt", () => {
      render(<ResearchDialog />)
      dispatchOpen({ mode: "schedule" })

      const preview = screen.getByTestId("research-dialog-preview-run") as HTMLButtonElement
      expect(preview.disabled).toBe(true)

      fireEvent.change(
        screen.getByPlaceholderText("What would you like to research?"),
        { target: { value: "A prompt" } }
      )
      expect(preview.disabled).toBe(false)
    })

    test("defaults back to once mode on reopen via bare event", () => {
      render(<ResearchDialog />)
      dispatchOpen({ mode: "schedule" })
      expect(screen.getByRole("button", { name: "Create schedule" })).toBeInTheDocument()

      fireEvent.keyDown(screen.getByTestId("research-dialog-form"), { key: "Escape" })
      dispatchOpen()

      expect(screen.getByLabelText("Submit research")).toBeInTheDocument()
      expect(screen.queryByRole("tab", { name: "Weekly" })).toBeNull()
    })
  })

  describe("schedule edit mode", () => {
    beforeEach(() => {
      setPathname("/scheduled_research")
    })

    test("populates the form from the schedule in the open event", () => {
      render(<ResearchDialog />)
      const schedule = makeSchedule({
        prompt: "Existing prompt",
        frequency: ScheduledResearchFrequency.DAILY,
        hour: 14,
        day_of_week: null,
      })
      dispatchOpen({ schedule })

      const textarea = screen.getByPlaceholderText("What would you like to research?") as HTMLTextAreaElement
      expect(textarea.value).toBe("Existing prompt")
      expect(screen.getByRole("tab", { name: "Daily", selected: true })).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument()
      expect(screen.queryByRole("button", { name: "Create schedule" })).toBeNull()
    })

    test("hides suggestion pills and the Schedule toggle chip", () => {
      render(<ResearchDialog />)
      dispatchOpen({ schedule: makeSchedule() })

      expect(screen.queryByText("Catch me up on last week")).toBeNull()
      expect(screen.queryByTestId("research-dialog-schedule-toggle")).toBeNull()
      expect(screen.getByTestId("scheduled-research-delete")).toBeInTheDocument()
      expect(screen.getByTestId("research-dialog-run-now")).toBeInTheDocument()
    })

    test("clears the prompt on reopen after a successful save", async () => {
      const updated = makeSchedule({ prompt: "Edited prompt" })
      mockApiFetch.mockResolvedValue(updated)

      render(<ResearchDialog />)
      dispatchOpen({ schedule: makeSchedule({ id: "sched-42", prompt: "Original prompt" }) })

      fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

      await waitFor(() => {
        expect(screen.queryByTestId("research-dialog-form")).toBeNull()
      })

      dispatchOpen()
      const textarea = screen.getByPlaceholderText("What would you like to research?") as HTMLTextAreaElement
      expect(textarea.value).toBe("")
    })

    test("Save changes PATCHes and dispatches an updated event, then closes", async () => {
      const updated = makeSchedule({ prompt: "Updated prompt" })
      mockApiFetch.mockResolvedValue(updated)
      const changes: ScheduledResearchChangedDetail[] = []
      const listener = (event: Event) =>
        changes.push((event as CustomEvent<ScheduledResearchChangedDetail>).detail)
      window.addEventListener(SCHEDULED_RESEARCH_CHANGED_EVENT, listener)

      render(<ResearchDialog />)
      dispatchOpen({ schedule: makeSchedule({ id: "sched-42" }) })

      const textarea = screen.getByPlaceholderText("What would you like to research?") as HTMLTextAreaElement
      fireEvent.change(textarea, { target: { value: "Updated prompt" } })
      fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith("/api/scheduled_research/sched-42", {
          method: "PATCH",
          body: JSON.stringify({
            prompt: "Updated prompt",
            frequency: ScheduledResearchFrequency.WEEKLY,
            hour: 9,
            day_of_week: "1",
          }),
        })
      })
      await waitFor(() => {
        expect(changes).toEqual([{ action: "updated", item: updated }])
      })
      expect(window.location.assign).not.toHaveBeenCalled()
      expect(screen.queryByTestId("research-dialog-form")).toBeNull()

      window.removeEventListener(SCHEDULED_RESEARCH_CHANGED_EVENT, listener)
    })

    test("Delete: confirm → DELETE → deleted event → closes", async () => {
      mockApiFetch.mockResolvedValue(undefined)
      const changes: ScheduledResearchChangedDetail[] = []
      const listener = (event: Event) =>
        changes.push((event as CustomEvent<ScheduledResearchChangedDetail>).detail)
      window.addEventListener(SCHEDULED_RESEARCH_CHANGED_EVENT, listener)
      confirmMock.mockResolvedValueOnce(true)

      render(<ResearchDialog />)
      dispatchOpen({ schedule: makeSchedule({ id: "sched-42" }) })

      fireEvent.click(screen.getByTestId("scheduled-research-delete"))

      expect(confirmMock).toHaveBeenCalledWith({ message: "Delete this schedule?" })

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith("/api/scheduled_research/sched-42", {
          method: "DELETE",
        })
      })
      await waitFor(() => {
        expect(changes).toEqual([{ action: "deleted", id: "sched-42" }])
      })
      expect(screen.queryByTestId("research-dialog-form")).toBeNull()

      window.removeEventListener(SCHEDULED_RESEARCH_CHANGED_EVENT, listener)
    })

    test("Delete: confirm cancel leaves the dialog open and doesn't fetch", async () => {
      confirmMock.mockResolvedValueOnce(false)

      render(<ResearchDialog />)
      dispatchOpen({ schedule: makeSchedule({ id: "sched-42" }) })

      fireEvent.click(screen.getByTestId("scheduled-research-delete"))

      await waitFor(() => expect(confirmMock).toHaveBeenCalled())
      expect(mockApiFetch).not.toHaveBeenCalled()
      expect(screen.getByTestId("research-dialog-form")).toBeInTheDocument()
    })

    test("Run now POSTs and shows the transient Enqueued label without closing", async () => {
      mockApiFetch.mockResolvedValue(undefined)

      render(<ResearchDialog />)
      dispatchOpen({ schedule: makeSchedule({ id: "sched-42" }) })

      const runNow = screen.getByTestId("research-dialog-run-now") as HTMLButtonElement
      expect(runNow).toHaveTextContent("Run now")

      fireEvent.click(runNow)

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith("/api/scheduled_research/sched-42/run_now", {
          method: "POST",
        })
      })
      await waitFor(() => {
        expect(runNow).toHaveTextContent("Enqueued")
      })
      // Dialog stays open through run-now.
      expect(screen.getByTestId("research-dialog-form")).toBeInTheDocument()
    })
  })
})
