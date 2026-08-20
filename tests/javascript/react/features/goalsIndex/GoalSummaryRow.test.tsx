import { cleanup, screen, fireEvent } from "@testing-library/react"
import { useState } from "react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { GoalSummaryRow } from "~/react/features/goalsIndex/components/GoalSummaryRow"
import type { Goal, Group, Subgoal, User } from "~/react/shared/types"

import { renderInGoalsRouter } from "./harness"

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

function makeSubgoal(overrides: Partial<Subgoal> = {}): Subgoal {
  return {
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
    ...overrides,
  }
}

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
]

const orgGroups: Group[] = [
  { id: "group-1", name: "Engineering" },
  { id: "group-2", name: "Design" },
]

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

interface RowWrapperProps {
  goal: Goal
  onGoalUpdated: (goal: Goal) => void
  onGoalRemoved: (goalId: string) => void
  onReorderSubgoals: (parentId: string, subgoals: Subgoal[]) => void
  onToggleComments: (goalId: string | null) => void
  onStartEditing: () => void
}

function RowWrapper({
  goal,
  onGoalUpdated,
  onGoalRemoved,
  onReorderSubgoals,
  onToggleComments,
  onStartEditing,
}: RowWrapperProps) {
  const [isExpanded, setIsExpanded] = useState(true)
  return (
    <GoalSummaryRow
      goal={goal}
      isSortEnabled={false}
      isExpanded={isExpanded}
      onToggleExpanded={() => setIsExpanded(e => !e)}
      organizationUsers={orgUsers}
      organizationGroups={orgGroups}
      onGoalUpdated={onGoalUpdated}
      onGoalRemoved={onGoalRemoved}
      onReorderSubgoals={onReorderSubgoals}
      openCommentsGoalId={null}
      onToggleComments={onToggleComments}
      onStartEditing={onStartEditing}
    />
  )
}

// The row links to the goal with a typed <Link>, so it must mount inside the
// router as the /goals route's component.
async function renderRow(goal = makeGoal()) {
  const onGoalUpdated = vi.fn()
  const onGoalRemoved = vi.fn()
  const onReorderSubgoals = vi.fn()
  const onToggleComments = vi.fn()
  const onStartEditing = vi.fn()

  const result = await renderInGoalsRouter(() => (
    <RowWrapper
      goal={goal}
      onGoalUpdated={onGoalUpdated}
      onGoalRemoved={onGoalRemoved}
      onReorderSubgoals={onReorderSubgoals}
      onToggleComments={onToggleComments}
      onStartEditing={onStartEditing}
    />
  ))

  return { ...result, onGoalUpdated, onGoalRemoved, onToggleComments, onStartEditing }
}

describe("GoalSummaryRow", () => {
  test("renders goal title, description, owner, group, status, and date as static text", async () => {
    await renderRow()
    expect(screen.getByText("Q1 Milestone")).toBeTruthy()
    expect(screen.getByText("Launch the new product line")).toBeTruthy()
    expect(screen.getAllByText("@Alice").length).toBeGreaterThan(0)
    expect(screen.getAllByText("@Engineering").length).toBeGreaterThan(0)
    expect(screen.getAllByText("On Track").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Mar 15, 2026").length).toBeGreaterThan(0)
  })

  test("renders placeholders when owner, group, and date are null", async () => {
    await renderRow(makeGoal({ owner: null, group: null, target_date: null }))
    expect(screen.getAllByText("No assignee").length).toBeGreaterThan(0)
    expect(screen.getAllByText("No group").length).toBeGreaterThan(0)
    expect(screen.getAllByText("No date").length).toBeGreaterThan(0)
  })

  test("renders completed badge for completed goals", async () => {
    await renderRow(makeGoal({ is_completed: true }))
    expect(screen.getAllByText("Complete").length).toBeGreaterThan(0)
    expect(screen.getAllByText("check").length).toBeGreaterThan(0)
  })

  test("renders link to goal detail page", async () => {
    const { container } = await renderRow(makeGoal({ id: "abc-123" }))
    const link = container.querySelector("a[href='/goals/abc-123']")
    expect(link).toBeTruthy()
  })

  test("renders li with id for hash fragment navigation", async () => {
    const { container } = await renderRow(makeGoal({ id: "abc-123" }))
    const li = container.querySelector("li")
    expect(li?.id).toBe("goal-abc-123")
  })

  test("edit button calls onStartEditing", async () => {
    const { onStartEditing } = await renderRow()
    fireEvent.click(screen.getByLabelText("Edit goal"))
    expect(onStartEditing).toHaveBeenCalled()
  })

  test("subgoals are expanded by default", async () => {
    await renderRow(makeGoal({ subgoals: [makeSubgoal()] }))
    expect(screen.getByText("Subgoal one")).toBeTruthy()
  })

  test("chevron toggles subgoal visibility", async () => {
    await renderRow(makeGoal({ subgoals: [makeSubgoal()] }))
    expect(screen.getByText("Subgoal one")).toBeTruthy()

    fireEvent.click(screen.getByText("chevron_right"))
    expect(screen.queryByText("Subgoal one")).toBeNull()

    fireEvent.click(screen.getByText("chevron_right"))
    expect(screen.getByText("Subgoal one")).toBeTruthy()
  })

  test("no chevron when goal has no subgoals", async () => {
    await renderRow(makeGoal({ subgoals: [] }))
    expect(screen.queryByText("chevron_right")).toBeNull()
  })

  test("comment button calls onToggleComments", async () => {
    const { onToggleComments } = await renderRow()
    const buttons = screen.getAllByText("chat_bubble").map(el => el.closest("button")!)
    fireEvent.click(buttons[0])
    expect(onToggleComments).toHaveBeenCalledWith("goal-1")
  })
})

describe("SubgoalSummaryRow (via GoalSummaryRow)", () => {
  test("renders subgoal content as static text", async () => {
    await renderRow(
      makeGoal({
        subgoals: [
          makeSubgoal({
            title: "Sub Title",
            description: "Sub description",
            owner: { id: "user-2", display_name: "Bob", picture: null },
            group: { id: "group-2", name: "Design" },
            target_date: "2026-06-01",
          }),
        ],
      })
    )
    expect(screen.getByText("Sub Title")).toBeTruthy()
    expect(screen.getByText("Sub description")).toBeTruthy()
    expect(screen.getAllByText("@Bob").length).toBeGreaterThan(0)
    expect(screen.getAllByText("@Design").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Jun 01, 2026").length).toBeGreaterThan(0)
  })

  test("renders subgoal link to detail page", async () => {
    const { container } = await renderRow(makeGoal({ subgoals: [makeSubgoal({ id: "sub-xyz" })] }))
    const link = container.querySelector("a[href='/goals/sub-xyz']")
    expect(link).toBeTruthy()
  })

  test("subgoal has independent edit toggle", async () => {
    await renderRow(makeGoal({ subgoals: [makeSubgoal()] }))
    const editButtons = screen.getAllByLabelText(/Edit (goal|subgoal)/)
    expect(editButtons.length).toBe(2)
  })
})
