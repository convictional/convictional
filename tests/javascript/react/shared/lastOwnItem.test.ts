import { describe, expect, it } from "vitest"

import { lastOwnItemId } from "~/react/shared/lastOwnItem"

type Item = { id: string; user: { id: string } | null }

const getUserId = (i: Item) => i.user?.id
const getId = (i: Item) => i.id

describe("lastOwnItemId", () => {
  it("returns the last item authored by the current user", () => {
    const items: Item[] = [
      { id: "a", user: { id: "me" } },
      { id: "b", user: { id: "other" } },
      { id: "c", user: { id: "me" } },
      { id: "d", user: { id: "other" } },
    ]
    expect(lastOwnItemId(items, "me", getUserId, getId)).toBe("c")
  })

  it("returns null when the user has no items", () => {
    const items: Item[] = [
      { id: "a", user: { id: "other" } },
      { id: "b", user: null },
    ]
    expect(lastOwnItemId(items, "me", getUserId, getId)).toBeNull()
  })

  it("returns null when there is no current user", () => {
    const items: Item[] = [{ id: "a", user: { id: "me" } }]
    expect(lastOwnItemId(items, null, getUserId, getId)).toBeNull()
  })

  it("returns null for an empty list", () => {
    expect(lastOwnItemId([], "me", getUserId, getId)).toBeNull()
  })
})
