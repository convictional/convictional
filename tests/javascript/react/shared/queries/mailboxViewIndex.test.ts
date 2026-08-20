import { describe, expect, it } from "vitest"

import {
  entryIdsFromSections,
  mailboxViewIndexFromResponse,
  mailboxViewIndexQueryKey,
  rankedSectionFromScores,
  slotSection,
} from "~/react/shared/queries/mailboxViewIndex"
import type { MailboxViewIndexResponse, ViewSection } from "~/react/shared/types"

function section(title: string, ids: string[]): ViewSection {
  return { title, description: "", mailbox_entry_ids: ids, goal: null }
}

function response(overrides: Partial<MailboxViewIndexResponse> = {}): MailboxViewIndexResponse {
  return {
    all_views: [],
    active: {
      kind: "template",
      id: "template:needs_reply",
      title: "Needs a reply",
      view_request: null,
      channel_id: "template:needs_reply",
      requires_goals: false,
      layout: "grouped",
    },
    cached_sections: null,
    cached_entry_ids: [],
    generating: false,
    has_goals_for_view: true,
    is_not_found: false,
    eligible_entry_count: null,
    considered_entry_count: null,
    ...overrides,
  }
}

describe("mailboxViewIndexQueryKey", () => {
  it("is stable and distinguishes identities, with empty-string slots for absent fields", () => {
    expect(mailboxViewIndexQueryKey({ viewId: "v1", template: null, goalId: null })).toEqual([
      "mailboxViewIndex",
      "v1",
      "",
      "",
    ])
    expect(mailboxViewIndexQueryKey({ viewId: null, template: "by_goal", goalId: "g1" })).toEqual([
      "mailboxViewIndex",
      "",
      "by_goal",
      "g1",
    ])
  })
})

describe("entryIdsFromSections", () => {
  it("flattens ids in section order", () => {
    expect(entryIdsFromSections([section("A", ["1", "2"]), section("B", ["3"])])).toEqual(["1", "2", "3"])
  })

  it("skips sparse holes rather than crashing on them", () => {
    const sparse = slotSection(slotSection([], 2, section("C", ["3"])), 0, section("A", ["1"]))
    // Index 1 is a hole; iterating must skip it.
    expect(entryIdsFromSections(sparse)).toEqual(["1", "3"])
  })
})

describe("slotSection", () => {
  it("places a section at its index while leaving other slots as sparse holes", () => {
    const first = slotSection([], 2, section("C", ["3"]))
    // The array is length 3 but only index 2 is a real slot — 0 and 1 are holes,
    // not explicit undefined (map/flatMap must skip them).
    expect(first.length).toBe(3)
    expect(Object.keys(first)).toEqual(["2"])
    const second = slotSection(first, 0, section("A", ["1"]))
    expect(Object.keys(second)).toEqual(["0", "2"])
    expect(second[0].title).toBe("A")
    expect(second[2].title).toBe("C")
  })

  it("does not mutate the input array", () => {
    const input = slotSection([], 0, section("A", ["1"]))
    const output = slotSection(input, 1, section("B", ["2"]))
    expect(input.length).toBe(1)
    expect(output.length).toBe(2)
  })
})

describe("rankedSectionFromScores", () => {
  it("returns no sections when nothing is scored", () => {
    expect(rankedSectionFromScores(new Map())).toEqual([])
  })

  it("orders by score desc, then rank asc, then id — the server's (score, rank, id) tuple", () => {
    const scores = new Map([
      ["c", { score: 5, rank: 2 }],
      ["a", { score: 9, rank: 3 }],
      ["b", { score: 5, rank: 1 }],
      ["d", { score: 5, rank: 1 }], // ties b on (score, rank) → id breaks the tie
    ])
    expect(rankedSectionFromScores(scores)[0].mailbox_entry_ids).toEqual(["a", "b", "d", "c"])
  })

  it("sinks a missing rank to the bottom of its tie group (Infinity, not front)", () => {
    const scores = new Map([
      ["ranked", { score: 5, rank: 0 }],
      ["unranked", { score: 5, rank: undefined as unknown as number }],
    ])
    expect(rankedSectionFromScores(scores)[0].mailbox_entry_ids).toEqual(["ranked", "unranked"])
  })
})

describe("mailboxViewIndexFromResponse", () => {
  it("projects a settled cache hit and flags hadCachedSections true", () => {
    const data = mailboxViewIndexFromResponse(
      response({
        cached_sections: [section("A", ["1", "2"])],
        cached_entry_ids: ["1", "2"],
        generating: false,
      })
    )
    expect(data.hadCachedSections).toBe(true)
    expect(data.entryIds).toEqual(["1", "2"])
    expect(data.generating).toBe(false)
    expect(data.layout).toBe("grouped")
    // A settled cache hit is not a partial — its deltas must stay live, not frozen/reconciled.
    expect(data.hydratedFromPartial).toBe(false)
  })

  it("treats a cache miss with an active view as generating, with hadCachedSections false", () => {
    const data = mailboxViewIndexFromResponse(response({ cached_sections: null, cached_entry_ids: [] }))
    expect(data.hadCachedSections).toBe(false)
    expect(data.generating).toBe(true)
    expect(data.sections).toEqual([])
    expect(data.entryIds).toEqual([])
    // A cache miss streams in from empty — nothing partial to reconcile against.
    expect(data.hydratedFromPartial).toBe(false)
  })

  it("flags hydratedFromPartial only for a cache hit that reports itself still generating", () => {
    const partial = mailboxViewIndexFromResponse(
      response({ cached_sections: [section("A", ["1"])], cached_entry_ids: ["1"], generating: true })
    )
    expect(partial.hydratedFromPartial).toBe(true)
  })

  it("is not generating when no view is active (plain inbox dropdown fetch)", () => {
    const data = mailboxViewIndexFromResponse(response({ active: null, cached_sections: null }))
    expect(data.generating).toBe(false)
    expect(data.layout).toBeNull()
  })

  it("falls back to flattening sections when cached_entry_ids is empty", () => {
    const data = mailboxViewIndexFromResponse(
      response({ cached_sections: [section("A", ["1"]), section("B", ["2"])], cached_entry_ids: [] })
    )
    expect(data.entryIds).toEqual(["1", "2"])
  })
})
