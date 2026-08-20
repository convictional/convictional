import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import {
  GoalPicker,
  sectionGoals,
} from "../../../../../app/javascript/react/features/mailboxIndex/components/GoalPicker"
import type { GoalOption } from "../../../../../app/javascript/react/features/mailboxIndex/types"

afterEach(cleanup)

function goal(overrides: Partial<GoalOption> & { id: string }): GoalOption {
  return { title: overrides.id, ownerId: null, groupId: null, groupName: null, ...overrides }
}

describe("sectionGoals", () => {
  test("splits into assigned-to-me, my-group sections, and others", () => {
    const goals: GoalOption[] = [
      goal({ id: "mine", ownerId: "u1" }),
      goal({ id: "prod", groupId: "g-prod", groupName: "Product" }),
      goal({ id: "cs", groupId: "g-cs", groupName: "Customer Success" }), // a group I'm not in
      goal({ id: "ungrouped" }),
      goal({ id: "mine-in-group", ownerId: "u1", groupId: "g-prod", groupName: "Product" }),
    ]

    const { mine, groupSections, others } = sectionGoals(goals, "u1", ["g-prod"])

    // Owned goals go to "Assigned to me" only — an owned goal in one of my groups isn't duplicated.
    expect(mine.map(g => g.id)).toEqual(["mine", "mine-in-group"])
    expect(groupSections.map(s => ({ name: s.name, ids: s.goals.map(g => g.id) }))).toEqual([
      { name: "Product", ids: ["prod"] },
    ])
    // A non-member group's goal and the ungrouped goal fall to "others".
    expect(others.map(g => g.id)).toEqual(["cs", "ungrouped"])
  })

  test("with no current user, nothing is 'mine' and everything falls to others", () => {
    const { mine, groupSections, others } = sectionGoals([goal({ id: "a", ownerId: "u1" }), goal({ id: "b" })], null, [])
    expect(mine).toEqual([])
    expect(groupSections).toEqual([])
    expect(others.map(g => g.id)).toEqual(["a", "b"])
  })

  test("a group with no loaded goals produces no section", () => {
    expect(sectionGoals([goal({ id: "x" })], "u1", ["g-empty"]).groupSections).toEqual([])
  })
})

describe("GoalPicker", () => {
  test("renders section headers, filters by query, and reports the chosen goal", () => {
    const onSelect = vi.fn()
    render(
      <GoalPicker
        goals={[
          goal({ id: "mine", title: "My own goal", ownerId: "u1" }),
          goal({ id: "prod", title: "Ship mobile", groupId: "g-prod", groupName: "Product" }),
          goal({ id: "other", title: "Company OKR" }),
        ]}
        loading={false}
        selectedId={null}
        currentUserId="u1"
        myGroupIds={["g-prod"]}
        onSelect={onSelect}
      />
    )

    expect(screen.getByText("Assigned to me")).toBeInTheDocument()
    expect(screen.getByText("Product")).toBeInTheDocument()
    expect(screen.getByText("Other goals")).toBeInTheDocument()

    fireEvent.click(screen.getByText("My own goal"))
    expect(onSelect).toHaveBeenCalledWith("mine")

    fireEvent.change(screen.getByPlaceholderText("Search goals…"), { target: { value: "mobile" } })
    expect(screen.getByText("Ship mobile")).toBeInTheDocument()
    expect(screen.queryByText("My own goal")).toBeNull()
  })

  test("renders a flat list with no headers when there are no owned or group goals", () => {
    render(
      <GoalPicker
        goals={[goal({ id: "a", title: "Alpha" }), goal({ id: "b", title: "Beta" })]}
        loading={false}
        selectedId={null}
        currentUserId="u1"
        myGroupIds={[]}
        onSelect={vi.fn()}
      />
    )
    expect(screen.getByText("Alpha")).toBeInTheDocument()
    expect(screen.queryByText("Assigned to me")).toBeNull()
    expect(screen.queryByText("Other goals")).toBeNull()
  })

  test("shows a loading placeholder while goals load", () => {
    render(
      <GoalPicker goals={[]} loading selectedId={null} currentUserId="u1" myGroupIds={[]} onSelect={vi.fn()} />
    )
    expect(screen.getByText("Loading goals…")).toBeInTheDocument()
  })
})
