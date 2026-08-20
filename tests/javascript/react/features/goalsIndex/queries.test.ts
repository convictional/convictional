import { describe, expect, test } from "vitest"

import {
  appendGoalToPages,
  containsTopLevelGoal,
  type GoalsListData,
  goalsListUrl,
  mergePageOne,
  removeGoalFromPages,
  setGoalsInPages,
  setSubgoalsInPages,
  updateGoalInPages,
} from "~/react/features/goalsIndex/queries"
import type { Goal, GoalSummary } from "~/react/shared/types"

function makeSubgoal(id: string, overrides: Partial<GoalSummary> = {}): GoalSummary {
  return {
    id,
    workspace_id: "ws-1",
    title: `Subgoal ${id}`,
    description: "",
    status: "active",
    progress: 0,
    target_date: null,
    is_completed: false,
    is_closed: false,
    is_draft: false,
    owner: null,
    group: null,
    open_comment_count: 0,
    ...overrides,
  }
}

function makeGoal(id: string, overrides: Partial<Goal> = {}): Goal {
  return {
    id,
    workspace_id: "ws-1",
    title: `Goal ${id}`,
    description: "",
    status: "active",
    progress: 0,
    target_date: null,
    start_date: null,
    is_completed: false,
    is_closed: false,
    is_draft: false,
    planning_list_name: null,
    created_at: "2026-06-17T00:00:00Z",
    owner: null,
    group: null,
    open_comment_count: 0,
    parent_id: null,
    parent: null,
    subgoals: [],
    ...overrides,
  }
}

// Two cached pages, the shape a reader who has scrolled once holds.
function makeData(pages: Goal[][], planningListNames: string[] | null = null): GoalsListData {
  return {
    pages: pages.map((goals, i) => ({
      goals,
      planning_list_names: i === 0 ? planningListNames : null,
      next_cursor: i === pages.length - 1 ? null : `c${i + 1}`,
      has_more: i !== pages.length - 1,
    })),
    pageParams: pages.map((_page, i) => (i === 0 ? null : `c${i}`)),
  }
}

function pageIds(data: GoalsListData | undefined): string[][] {
  return (data?.pages ?? []).map(page => page.goals.map(g => g.id))
}

const NO_LOCAL_IDS = new Set<string>()

describe("goalsListUrl", () => {
  test("asks for the subgoal tree, and maps the view onto the API's own params", () => {
    expect(goalsListUrl("active", [], [])).toBe("/api/goals?expand=subgoals")
    expect(goalsListUrl("completed", [], [])).toContain("is_completed=true")
    expect(goalsListUrl("closed", [], [])).toContain("is_closed=true")
    expect(goalsListUrl("Q3 plan", [], [])).toContain("planning_list_name=Q3+plan")
  })

  test("sends array filters as repeated keys, not the router's JSON form", () => {
    const url = goalsListUrl("active", ["u1", "u2"], ["g1"], "cursor-1")
    expect(url).toContain("owner_ids=u1&owner_ids=u2")
    expect(url).toContain("group_ids=g1")
    expect(url).toContain("cursor=cursor-1")
  })
})

describe("goals list cache patches", () => {
  test("every helper is a no-op on an empty cache", () => {
    expect(updateGoalInPages(undefined, makeGoal("a"))).toBeUndefined()
    expect(removeGoalFromPages(undefined, "a")).toBeUndefined()
    expect(appendGoalToPages(undefined, makeGoal("a"))).toBeUndefined()
    expect(setGoalsInPages(undefined, [makeGoal("a")])).toBeUndefined()
    expect(setSubgoalsInPages(undefined, "a", [])).toBeUndefined()
    expect(mergePageOne(undefined, { goals: [], next_cursor: null, has_more: false }, NO_LOCAL_IDS)).toBeUndefined()
  })

  test("containsTopLevelGoal looks across every loaded page, but never into subgoals", () => {
    const data = makeData([[makeGoal("a", { subgoals: [makeSubgoal("s1")] })], [makeGoal("b")]])
    expect(containsTopLevelGoal(data, "b")).toBe(true)
    expect(containsTopLevelGoal(data, "z")).toBe(false)
    expect(containsTopLevelGoal(data, "s1")).toBe(false)
  })

  test("updateGoalInPages replaces a goal wherever it sits, and summarizes it into its parent", () => {
    const data = makeData([[makeGoal("a", { subgoals: [makeSubgoal("s1")] })], [makeGoal("b")]])

    const updatedTop = updateGoalInPages(data, makeGoal("b", { description: "Edited" }))
    expect(updatedTop!.pages[1].goals[0].description).toBe("Edited")

    const updatedSub = updateGoalInPages(data, makeGoal("s1", { title: "Renamed" }))
    expect(updatedSub!.pages[0].goals[0].subgoals!.map(s => s.title)).toEqual(["Renamed"])
  })

  test("removeGoalFromPages drops a top-level goal, or a subgoal from its parent", () => {
    const data = makeData([[makeGoal("a", { subgoals: [makeSubgoal("s1"), makeSubgoal("s2")] })], [makeGoal("b")]])

    expect(pageIds(removeGoalFromPages(data, "b"))).toEqual([["a"], []])

    const withoutSubgoal = removeGoalFromPages(data, "s1")
    expect(pageIds(withoutSubgoal)).toEqual([["a"], ["b"]])
    expect(withoutSubgoal!.pages[0].goals[0].subgoals!.map(s => s.id)).toEqual(["s2"])
  })

  test("appendGoalToPages puts a new goal at the very end, since it sorts last server-side", () => {
    const data = makeData([[makeGoal("a")], [makeGoal("b")]])
    expect(pageIds(appendGoalToPages(data, makeGoal("new")))).toEqual([["a"], ["b", "new"]])
  })

  test("setGoalsInPages writes a reordered flat list back at the original page lengths", () => {
    const data = makeData([[makeGoal("a"), makeGoal("b")], [makeGoal("c")]])
    const reordered = [makeGoal("c"), makeGoal("a"), makeGoal("b")]
    expect(pageIds(setGoalsInPages(data, reordered))).toEqual([["c", "a"], ["b"]])
  })

  test("setSubgoalsInPages replaces only the named parent's subgoals", () => {
    const data = makeData([[makeGoal("a", { subgoals: [makeSubgoal("s1")] }), makeGoal("b")]])
    const patched = setSubgoalsInPages(data, "a", [makeSubgoal("s2"), makeSubgoal("s1")])
    expect(patched!.pages[0].goals[0].subgoals!.map(s => s.id)).toEqual(["s2", "s1"])
    expect(patched!.pages[0].goals[1].subgoals).toEqual([])
  })
})

describe("mergePageOne", () => {
  const twoPages = () => makeData([[makeGoal("a"), makeGoal("b")], [makeGoal("c")]], ["Q3"])

  test("replaces page 1 and leaves later pages frozen", () => {
    const merged = mergePageOne(
      twoPages(),
      { goals: [makeGoal("b"), makeGoal("a")], next_cursor: "c1", has_more: true },
      NO_LOCAL_IDS
    )
    expect(pageIds(merged)).toEqual([["b", "a"], ["c"]])
    expect(merged!.pages[0].next_cursor).toBe("c1")
    expect(merged!.pages[0].has_more).toBe(true)
  })

  test("keeps a locally created goal the payload hasn't paged in yet, appended after it", () => {
    const data = makeData([[makeGoal("a"), makeGoal("new")]])
    const merged = mergePageOne(data, { goals: [makeGoal("a")], next_cursor: null, has_more: false }, new Set(["new"]))
    expect(pageIds(merged)).toEqual([["a", "new"]])
  })

  test("drops the page-1 copy once the server pages the goal onto a later page", () => {
    // The create appended it to the loaded tail; the next page-1 listing pushed a
    // page boundary past it, so the authoritative row is already on page 2.
    const data = makeData([[makeGoal("a"), makeGoal("new")], [makeGoal("new")]])
    const merged = mergePageOne(data, { goals: [makeGoal("a")], next_cursor: "c1", has_more: true }, new Set(["new"]))
    expect(pageIds(merged)).toEqual([["a"], ["new"]])
  })

  test("drops a goal that is simply gone from the view", () => {
    // Not local-only, absent from the payload: closed or reassigned elsewhere.
    const merged = mergePageOne(
      makeData([[makeGoal("a"), makeGoal("b")]]),
      { goals: [makeGoal("a")], next_cursor: null, has_more: false },
      NO_LOCAL_IDS
    )
    expect(pageIds(merged)).toEqual([["a"]])
  })

  test("keeps the cached planning list names when the payload omits them", () => {
    const fromChannel = mergePageOne(twoPages(), { goals: [], next_cursor: null, has_more: false }, NO_LOCAL_IDS)
    expect(fromChannel!.pages[0].planning_list_names).toEqual(["Q3"])

    const fromRefetch = mergePageOne(
      twoPages(),
      { goals: [], next_cursor: null, has_more: false, planning_list_names: ["Q4"] },
      NO_LOCAL_IDS
    )
    expect(fromRefetch!.pages[0].planning_list_names).toEqual(["Q4"])
  })
})
