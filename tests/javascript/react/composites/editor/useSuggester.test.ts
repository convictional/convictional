import { expect, test, describe, vi } from "vitest"
import Fuse from "fuse.js"

// Test the search logic that useSuggester uses internally.
// The hook itself depends on ProseMirror and can't run in jsdom,
// but the Fuse.js filtering is the core logic worth covering.

interface Item {
  name: string
  category: string
}

const items: Item[] = [
  { name: "Alice", category: "admin" },
  { name: "Bob", category: "user" },
  { name: "Charlie", category: "user" },
  { name: "Alicia", category: "admin" },
  { name: "David", category: "user" },
]

const fuse = new Fuse(items, { keys: ["name"], threshold: 0.3 })
const MAX_RESULTS = 20

function search(query: string): Item[] {
  if (!query) return items.slice(0, MAX_RESULTS)
  return fuse
    .search(query)
    .map(r => r.item)
    .slice(0, MAX_RESULTS)
}

describe("suggester search logic", () => {
  test("returns all items when query is empty", () => {
    const results = search("")
    expect(results).toHaveLength(5)
  })

  test("filters by fuzzy match", () => {
    const results = search("ali")
    expect(results.map(r => r.name)).toContain("Alice")
    expect(results.map(r => r.name)).toContain("Alicia")
    expect(results.map(r => r.name)).not.toContain("Bob")
  })

  test("returns empty for no matches", () => {
    const results = search("zzzzz")
    expect(results).toHaveLength(0)
  })

  test("respects max results limit", () => {
    const manyItems = Array.from({ length: 50 }, (_, i) => ({ name: `user${i}`, category: "user" }))
    const manyFuse = new Fuse(manyItems, { keys: ["name"], threshold: 0.3 })

    const results = manyFuse
      .search("user")
      .map(r => r.item)
      .slice(0, MAX_RESULTS)
    expect(results.length).toBeLessThanOrEqual(MAX_RESULTS)
  })
})

// Mirrors the exit-branch dedup guard in useSuggester's onChange callback.
// The hook itself can't run in jsdom (ProseMirror dependency), so we
// extract and test the guard as a pure function.
function shouldProcessExit(lastChange: { from: number; to: number } | null): {
  process: boolean
  newLastChange: null
} {
  // Mirrors the fixed exit branch in useSuggester.ts:
  // if (lastChangeRef.current === null) return — skip re-entrant exits
  if (lastChange === null) return { process: false, newLastChange: null }
  return { process: true, newLastChange: null }
}

describe("exit-branch dedup guard", () => {
  test("skips setState when exit fires repeatedly with lastChange already null", () => {
    const setState = vi.fn()

    // Simulate first exit after an active suggestion (lastChange is non-null)
    const firstChange = { from: 5, to: 10 }
    const first = shouldProcessExit(firstChange)
    if (first.process) setState({ shouldShow: false })

    // First exit should call setState
    expect(setState).toHaveBeenCalledTimes(1)

    // Simulate second exit (re-entrant call) — lastChange is now null
    const second = shouldProcessExit(first.newLastChange)
    if (second.process) setState({ shouldShow: false })

    // The dedup guard prevents the second setState call — re-entrant
    // exit with lastChange=null is a no-op.
    expect(setState).toHaveBeenCalledTimes(1)
  })
})
