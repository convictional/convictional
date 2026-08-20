import { cleanup, render, screen, fireEvent, waitFor, act } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { GoalEditRow } from "../../../../../app/javascript/react/features/goalsIndex/components/GoalEditRow"
import type { Goal, Group, User } from "../../../../../app/javascript/react/shared/types"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
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

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
const mockApiFetch = vi.mocked(apiFetch)

function makeGoal(overrides: Partial<Goal> = {}): Goal {
  return {
    id: "goal-1",
    workspace_id: "ws-1",
    title: "Q1 Milestone",
    description: "Launch the new product line",
    status: "on_track",
    progress: 0.5,
    target_date: "2026-03-15",
    start_date: "2026-01-01",
    is_completed: false,
    is_closed: false,
    is_draft: false,
    planning_list_name: null,
    created_at: "2026-01-01T00:00:00Z",
    owner: { id: "user-1", display_name: "Alice", picture: null },
    group: { id: "group-1", name: "Engineering" },
    open_comment_count: 0,
    subgoals: [],
    ...overrides,
  }
}

const orgUsers: User[] = [
  { id: "user-1", display_name: "Alice", picture: null },
  { id: "user-2", display_name: "Bob", picture: null },
  { id: "user-3", display_name: "Charlie", picture: null },
]

const orgGroups: Group[] = [
  { id: "group-1", name: "Engineering" },
  { id: "group-2", name: "Design" },
]

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderGoalRow(goal = makeGoal(), onGoalUpdated = vi.fn(), isHighlighted?: boolean) {
  return {
    onGoalUpdated,
    ...render(
      <GoalEditRow
        goal={goal}
        isPlanningList={false}
        isSortEnabled={false}
        isHighlighted={isHighlighted}
        organizationUsers={orgUsers}
        organizationGroups={orgGroups}
        onGoalUpdated={onGoalUpdated}
        onGoalRemoved={vi.fn()}
        onReorderSubgoals={vi.fn()}
        openCommentsGoalId={null}
        onToggleComments={vi.fn()}
      />
    ),
  }
}

describe("GoalEditRow", () => {
  test("renders goal title, description, owner, group, status, and date", () => {
    renderGoalRow()
    expect(screen.getByText("Q1 Milestone")).toBeTruthy()
    expect(screen.getByText("Launch the new product line")).toBeTruthy()
    expect(screen.getAllByText("@Alice").length).toBeGreaterThan(0)
    expect(screen.getAllByText("@Engineering").length).toBeGreaterThan(0)
    expect(screen.getAllByText("On Track").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Mar 15, 2026").length).toBeGreaterThan(0)
  })

  test("renders 'No assignee' when owner is null", () => {
    renderGoalRow(makeGoal({ owner: null }))
    expect(screen.getAllByText("No assignee").length).toBeGreaterThan(0)
  })

  test("renders 'No group' when group is null", () => {
    renderGoalRow(makeGoal({ group: null }))
    expect(screen.getAllByText("No group").length).toBeGreaterThan(0)
  })

  test("renders 'No date' when target_date is null", () => {
    renderGoalRow(makeGoal({ target_date: null }))
    expect(screen.getAllByText("No date").length).toBeGreaterThan(0)
  })

  test("hides status dropdown on planning lists", () => {
    render(
      <GoalEditRow
        goal={makeGoal()}
        isPlanningList={true}
        isSortEnabled={false}
        organizationUsers={orgUsers}
        organizationGroups={orgGroups}
        onGoalUpdated={vi.fn()}
        onGoalRemoved={vi.fn()}
        onReorderSubgoals={vi.fn()}
        openCommentsGoalId={null}
        onToggleComments={vi.fn()}
      />
    )
    expect(screen.queryByText("On Track")).toBeNull()
  })

  test("does not show chevron when goal has no subgoals", () => {
    renderGoalRow(makeGoal({ subgoals: [] }))
    expect(screen.queryByText("chevron_right")).toBeNull()
  })

  test("shows chevron and toggles subgoal visibility", () => {
    const goalWithSubgoals = makeGoal({
      subgoals: [
        {
          id: "sub-1",
          workspace_id: "ws-1",
          title: null,
          description: "Subgoal one",
          status: "on_track",
          progress: 0,
          target_date: null,
          is_completed: false,
          is_draft: false,
          owner: null,
          group: null,
          open_comment_count: 0,
        },
      ],
    })
    renderGoalRow(goalWithSubgoals)
    expect(screen.getByText("chevron_right")).toBeTruthy()
    // Subgoals hidden by default (defaultExpanded not set)
    expect(screen.queryByText("Subgoal one")).toBeNull()

    fireEvent.click(screen.getByText("chevron_right"))
    expect(screen.getByText("Subgoal one")).toBeTruthy()

    fireEvent.click(screen.getByText("chevron_right"))
    expect(screen.queryByText("Subgoal one")).toBeNull()
  })

  test("renders li with id matching goal-{id} for hash fragment navigation", () => {
    const { container } = renderGoalRow(makeGoal({ id: "abc-123" }))
    const li = container.querySelector("li")
    expect(li?.id).toBe("goal-abc-123")
  })
})

describe("GoalDescriptionEditor", () => {
  test("clicking title enters edit mode with input", () => {
    renderGoalRow()
    fireEvent.click(screen.getByText("Q1 Milestone"))
    const input = screen.getByDisplayValue("Q1 Milestone")
    expect(input.tagName).toBe("INPUT")
  })

  test("pressing Escape cancels title edit without saving", () => {
    renderGoalRow()
    fireEvent.click(screen.getByText("Q1 Milestone"))
    const input = screen.getByDisplayValue("Q1 Milestone")
    fireEvent.change(input, { target: { value: "Changed" } })
    fireEvent.keyDown(input, { key: "Escape" })
    expect(screen.getByText("Q1 Milestone")).toBeTruthy()
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  test("pressing Enter saves title via PATCH", async () => {
    const updatedGoal = makeGoal({ title: "New Title" })
    mockApiFetch.mockResolvedValue(updatedGoal)
    const { onGoalUpdated } = renderGoalRow()

    fireEvent.click(screen.getByText("Q1 Milestone"))
    const input = screen.getByDisplayValue("Q1 Milestone")
    fireEvent.change(input, { target: { value: "New Title" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/goal-1?expand=subgoals&expand=parent", {
        method: "PATCH",
        body: JSON.stringify({ title: "New Title" }),
      })
    })
    expect(onGoalUpdated).toHaveBeenCalledWith(updatedGoal)
  })

  test("title not saved when value unchanged", () => {
    renderGoalRow()
    fireEvent.click(screen.getByText("Q1 Milestone"))
    const input = screen.getByDisplayValue("Q1 Milestone")
    fireEvent.keyDown(input, { key: "Enter" })
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  test("clicking description enters edit mode with textarea", () => {
    renderGoalRow()
    fireEvent.click(screen.getByText("Launch the new product line"))
    const textarea = screen.getByDisplayValue("Launch the new product line")
    expect(textarea.tagName).toBe("TEXTAREA")
  })

  test("pressing Escape cancels description edit", () => {
    renderGoalRow()
    fireEvent.click(screen.getByText("Launch the new product line"))
    const input = screen.getByDisplayValue("Launch the new product line")
    fireEvent.change(input, { target: { value: "Changed" } })
    fireEvent.keyDown(input, { key: "Escape" })
    expect(screen.getByText("Launch the new product line")).toBeTruthy()
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  test("description auto-saves after debounce", async () => {
    vi.useFakeTimers()
    const updatedGoal = makeGoal({ description: "Updated description" })
    mockApiFetch.mockResolvedValue(updatedGoal)
    const { onGoalUpdated } = renderGoalRow()

    fireEvent.click(screen.getByText("Launch the new product line"))
    const input = screen.getByDisplayValue("Launch the new product line")
    fireEvent.change(input, { target: { value: "Updated description" } })

    expect(mockApiFetch).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })

    expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/goal-1?expand=subgoals&expand=parent", {
      method: "PATCH",
      body: JSON.stringify({ description: "Updated description" }),
    })
    expect(onGoalUpdated).toHaveBeenCalledWith(updatedGoal)

    vi.useRealTimers()
  })

  test("description not saved when empty", async () => {
    vi.useFakeTimers()
    renderGoalRow()

    fireEvent.click(screen.getByText("Launch the new product line"))
    const input = screen.getByDisplayValue("Launch the new product line")
    fireEvent.change(input, { target: { value: "   " } })

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })

    expect(mockApiFetch).not.toHaveBeenCalled()
    vi.useRealTimers()
  })
})

describe("OwnerPicker", () => {
  test("clicking owner opens dropdown with search and user list", () => {
    renderGoalRow()
    fireEvent.click(screen.getAllByText("@Alice")[0])
    expect(screen.getByPlaceholderText("Search people...")).toBeTruthy()
    expect(screen.getByText("Current Owner")).toBeTruthy()
    expect(screen.getByText("Bob")).toBeTruthy()
    expect(screen.getByText("Charlie")).toBeTruthy()
  })

  test("search filters the user list", () => {
    renderGoalRow()
    fireEvent.click(screen.getAllByText("@Alice")[0])
    const search = screen.getByPlaceholderText("Search people...")
    fireEvent.change(search, { target: { value: "Bob" } })
    expect(screen.getByText("Bob")).toBeTruthy()
    expect(screen.queryByText("Charlie")).toBeNull()
  })

  test("selecting a user sends PATCH with owner_id", async () => {
    const updatedGoal = makeGoal({ owner: { id: "user-2", display_name: "Bob", picture: null } })
    mockApiFetch.mockResolvedValue(updatedGoal)
    const { onGoalUpdated } = renderGoalRow()

    fireEvent.click(screen.getAllByText("@Alice")[0])
    fireEvent.click(screen.getByText("Bob"))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/goal-1?expand=subgoals&expand=parent", {
        method: "PATCH",
        body: JSON.stringify({ owner_id: "user-2" }),
      })
    })
    expect(onGoalUpdated).toHaveBeenCalledWith(updatedGoal)
  })

  test("clearing owner sends PATCH with clear_owner", async () => {
    const updatedGoal = makeGoal({ owner: null })
    mockApiFetch.mockResolvedValue(updatedGoal)
    const { onGoalUpdated } = renderGoalRow()

    fireEvent.click(screen.getAllByText("@Alice")[0])
    // Click the current owner row (which has the close icon)
    const closeButtons = screen.getAllByText("close")
    fireEvent.click(closeButtons[0])

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/goal-1?expand=subgoals&expand=parent", {
        method: "PATCH",
        body: JSON.stringify({ clear_owner: true }),
      })
    })
    expect(onGoalUpdated).toHaveBeenCalledWith(updatedGoal)
  })
})

describe("GroupPicker", () => {
  test("clicking group opens dropdown with search", () => {
    renderGoalRow()
    fireEvent.click(screen.getAllByText("@Engineering")[0])
    expect(screen.getByPlaceholderText("Search groups...")).toBeTruthy()
    expect(screen.getByText("Current Group")).toBeTruthy()
    expect(screen.getByText("Design")).toBeTruthy()
  })

  test("selecting a group sends PATCH with group_id", async () => {
    const updatedGoal = makeGoal({ group: { id: "group-2", name: "Design" } })
    mockApiFetch.mockResolvedValue(updatedGoal)
    const { onGoalUpdated } = renderGoalRow()

    fireEvent.click(screen.getAllByText("@Engineering")[0])
    fireEvent.click(screen.getByText("Design"))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/goal-1?expand=subgoals&expand=parent", {
        method: "PATCH",
        body: JSON.stringify({ group_id: "group-2" }),
      })
    })
    expect(onGoalUpdated).toHaveBeenCalledWith(updatedGoal)
  })
})

describe("StatusDropdown", () => {
  test("clicking status badge opens dropdown with all options", () => {
    renderGoalRow()
    fireEvent.click(screen.getAllByText("On Track")[0])
    expect(screen.getByText("At Risk")).toBeTruthy()
    expect(screen.getByText("Off Track")).toBeTruthy()
    expect(screen.getByText("Complete")).toBeTruthy()
  })

  test("selecting a status sends PATCH", async () => {
    const updatedGoal = makeGoal({ status: "at_risk" })
    mockApiFetch.mockResolvedValue(updatedGoal)
    const { onGoalUpdated } = renderGoalRow()

    fireEvent.click(screen.getAllByText("On Track")[0])
    fireEvent.click(screen.getByText("At Risk"))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/goal-1?expand=subgoals&expand=parent", {
        method: "PATCH",
        body: JSON.stringify({ is_completed: false, status: "at_risk" }),
      })
    })
    expect(onGoalUpdated).toHaveBeenCalledWith(updatedGoal)
  })

  test("selecting Complete sends is_completed true without status", async () => {
    const updatedGoal = makeGoal({ is_completed: true })
    mockApiFetch.mockResolvedValue(updatedGoal)
    const { onGoalUpdated } = renderGoalRow()

    fireEvent.click(screen.getAllByText("On Track")[0])
    fireEvent.click(screen.getByText("Complete"))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/goal-1?expand=subgoals&expand=parent", {
        method: "PATCH",
        body: JSON.stringify({ is_completed: true }),
      })
    })
    expect(onGoalUpdated).toHaveBeenCalledWith(updatedGoal)
  })

  test("completed goal shows Complete badge with check icon", () => {
    renderGoalRow(makeGoal({ is_completed: true }))
    expect(screen.getAllByText("Complete").length).toBeGreaterThan(0)
    expect(screen.getAllByText("check").length).toBeGreaterThan(0)
  })
})

describe("TargetDatePicker", () => {
  test("clicking date opens calendar with month and day grid", () => {
    renderGoalRow()
    fireEvent.click(screen.getAllByText("Mar 15, 2026")[0])
    expect(screen.getByText("March")).toBeTruthy()
    expect(screen.getByText("2026")).toBeTruthy()
    expect(screen.getByText("Su")).toBeTruthy()
    expect(screen.getByText("15")).toBeTruthy()
    expect(screen.getByText("Clear date")).toBeTruthy()
  })

  test("selecting a day sends PATCH with target_date", async () => {
    const updatedGoal = makeGoal({ target_date: "2026-03-20" })
    mockApiFetch.mockResolvedValue(updatedGoal)
    const { onGoalUpdated } = renderGoalRow()

    fireEvent.click(screen.getAllByText("Mar 15, 2026")[0])
    fireEvent.click(screen.getByText("20"))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/goal-1?expand=subgoals&expand=parent", {
        method: "PATCH",
        body: JSON.stringify({ target_date: "2026-03-20" }),
      })
    })
    expect(onGoalUpdated).toHaveBeenCalledWith(updatedGoal)
  })

  test("clearing date sends PATCH with clear_target_date", async () => {
    const updatedGoal = makeGoal({ target_date: null })
    mockApiFetch.mockResolvedValue(updatedGoal)
    const { onGoalUpdated } = renderGoalRow()

    fireEvent.click(screen.getAllByText("Mar 15, 2026")[0])
    fireEvent.click(screen.getByText("Clear date"))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/goal-1?expand=subgoals&expand=parent", {
        method: "PATCH",
        body: JSON.stringify({ clear_target_date: true }),
      })
    })
    expect(onGoalUpdated).toHaveBeenCalledWith(updatedGoal)
  })

  test("month navigation works", () => {
    renderGoalRow()
    fireEvent.click(screen.getAllByText("Mar 15, 2026")[0])
    expect(screen.getByText("March")).toBeTruthy()

    const calendarPrev = screen.getByText("chevron_left").closest("button")!
    const calendarNext = screen.getByText("chevron_right").closest("button")!

    fireEvent.click(calendarPrev)
    expect(screen.getByText("February")).toBeTruthy()

    fireEvent.click(calendarNext)
    expect(screen.getByText("March")).toBeTruthy()

    fireEvent.click(calendarNext)
    expect(screen.getByText("April")).toBeTruthy()
  })
})
