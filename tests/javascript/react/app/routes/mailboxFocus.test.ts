import { describe, expect, it } from "vitest"

import { focusParams, inboxSearch } from "~/react/app/routes/mailboxFocus"

// The client half of the inbox focus-preference contract. The server half
// (app/helpers/mailbox_focus.py) is covered by
// tests/integration/routers/api/test_mailbox_focus.py; these are the mappings that
// used to be exercised through GET / and so have no server-side test left.

describe("inboxSearch", () => {
  it("keeps sort=newest in the URL", () => {
    // "/?sort=newest" is the clear-focus action: normalizing it away would make
    // clearing a focus a no-op, since the stored "sort=newest" is what defeats a
    // saved view on the next read.
    expect(inboxSearch({ sort: "newest" }).sort).toBe("newest")
    expect(inboxSearch({ sort: "oldest" }).sort).toBe("oldest")
  })

  it("drops a sort it doesn't recognize", () => {
    expect(inboxSearch({ sort: "sideways" }).sort).toBeUndefined()
    expect(inboxSearch({}).sort).toBeUndefined()
  })

  it("passes the focus selector through and ignores non-string garbage", () => {
    expect(inboxSearch({ mailbox_view_id: "v1" }).mailbox_view_id).toBe("v1")
    expect(inboxSearch({ mailbox_view_template: "by_goal", goal_id: "g1" })).toMatchObject({
      mailbox_view_template: "by_goal",
      goal_id: "g1",
    })
    // The search parser coerces numeric-looking values, but ids are UUIDs.
    expect(inboxSearch({ goal_id: 2026 }).goal_id).toBeUndefined()
    expect(inboxSearch({ mailbox_view_id: "" }).mailbox_view_id).toBeUndefined()
  })
})

describe("focusParams", () => {
  // The all-null focus the endpoint returns for the default preference.
  const none = { sort: null, mailbox_view_template: null, goal_id: null, mailbox_view_id: null }

  // The endpoint encodes on presence with sort winning, so sending a sort that
  // validateSearch had defaulted would store "sort=newest" and silently drop the
  // view the user just picked. This is the precedence _preference_from_query used.
  it("keeps only the selector actually present", () => {
    expect(focusParams({ mailbox_view_id: "v1" })).toEqual({ mailbox_view_id: "v1" })
    expect(focusParams({ mailbox_view_template: "urgent_important" })).toEqual({
      mailbox_view_template: "urgent_important",
    })
    expect(focusParams({ sort: "oldest" })).toEqual({ sort: "oldest" })
  })

  it("keeps template and goal together, since one key can't carry both", () => {
    expect(focusParams({ mailbox_view_template: "by_goal", goal_id: "g1" })).toEqual({
      mailbox_view_template: "by_goal",
      goal_id: "g1",
    })
  })

  it("lets sort win when the URL somehow carries both", () => {
    expect(focusParams({ sort: "newest", mailbox_view_id: "v1" })).toEqual({ sort: "newest" })
  })

  // Same precedence off the endpoint's response shape, which spells absence null
  // rather than undefined — this is the direction that builds the bare-"/" redirect.
  it("reads a resolved focus off the response shape", () => {
    expect(focusParams({ ...none, mailbox_view_id: "v1" })).toEqual({ mailbox_view_id: "v1" })
    expect(focusParams({ ...none, mailbox_view_template: "by_goal", goal_id: "g1" })).toEqual({
      mailbox_view_template: "by_goal",
      goal_id: "g1",
    })
    expect(focusParams({ ...none, sort: "oldest" })).toEqual({ sort: "oldest" })
  })

  it("is null for no focus, so bare / neither redirects nor persists", () => {
    // The endpoint returns sort: null rather than "newest" precisely so this is
    // null — an all-null focus means the bare inbox URL is already correct.
    expect(focusParams({})).toBeNull()
    expect(focusParams(none)).toBeNull()
  })
})
