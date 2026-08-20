import { describe, expect, it } from "vitest"

import { describeEmailActivity } from "~/react/features/mailboxIndex/components/entryBodies/emailActivityPreview"

const VIEWER = "user-me"

describe("describeEmailActivity", () => {
  it("returns null for draft schedule/unschedule so the row keeps the draft snippet", () => {
    expect(
      describeEmailActivity("draft_scheduled", null, { actorName: "Alice", actorId: "user-alice", currentUserId: VIEWER })
    ).toBeNull()
    expect(describeEmailActivity("draft_unscheduled", null, {})).toBeNull()
  })

  it("delegates cross-resource actions to the shared phrasing", () => {
    expect(
      describeEmailActivity(
        "added_collaborator",
        { collaborator: { id: "user-bob", name: "Bob", email: null } },
        { actorName: "Alice", actorId: "user-alice", currentUserId: VIEWER }
      )
    ).toBe("Alice added Bob")
  })

  it("falls back to a generic line for an unknown action", () => {
    expect(describeEmailActivity(null, null, {})).toBe("Updated this thread")
  })
})
