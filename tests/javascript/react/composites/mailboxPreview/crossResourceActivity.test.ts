import { describe, expect, it } from "vitest"

import { describeCrossResourceActivity } from "~/react/composites/mailboxPreview/crossResourceActivity"

const VIEWER = "user-me"
const collaborator = (id: string, name?: string) => ({
  collaborator: { id, name: name ?? null, email: name ? null : `${id}@example.com` },
})
const assignee = (id: string, name?: string) => ({
  assignee: { id, name: name ?? null, email: name ? null : `${id}@example.com` },
})

describe("describeCrossResourceActivity: added_collaborator", () => {
  it("says 'You added X' when the actor is the viewer", () => {
    expect(
      describeCrossResourceActivity("added_collaborator", collaborator("user-bob", "Bob"), {
        actorName: "Me",
        actorId: VIEWER,
        currentUserId: VIEWER,
      })
    ).toBe("You added Bob")
  })

  it("says 'Alice added X' when the actor is someone else", () => {
    expect(
      describeCrossResourceActivity("added_collaborator", collaborator("user-bob", "Bob"), {
        actorName: "Alice",
        actorId: "user-alice",
        currentUserId: VIEWER,
      })
    ).toBe("Alice added Bob")
  })

  it("says 'Alice added you' when the added person is the viewer", () => {
    expect(
      describeCrossResourceActivity("added_collaborator", collaborator(VIEWER, "Me"), {
        actorName: "Alice",
        actorId: "user-alice",
        currentUserId: VIEWER,
      })
    ).toBe("Alice added you")
  })

  it("falls back to 'Added X' when the actor is unknown", () => {
    expect(
      describeCrossResourceActivity("added_collaborator", collaborator("user-bob", "Bob"), {
        currentUserId: VIEWER,
      })
    ).toBe("Added Bob")
  })

  it("falls back to a generic line when neither party is known", () => {
    expect(describeCrossResourceActivity("added_collaborator", {}, { currentUserId: VIEWER })).toBe(
      "Added a collaborator"
    )
  })

  it("uses names (no viewer substitution) when the current user is unknown", () => {
    expect(
      describeCrossResourceActivity("added_collaborator", collaborator("user-bob", "Bob"), {
        actorName: "Alice",
        actorId: "user-alice",
      })
    ).toBe("Alice added Bob")
  })
})

describe("describeCrossResourceActivity: removed_collaborator", () => {
  it("says 'You removed X' when the actor is the viewer", () => {
    expect(
      describeCrossResourceActivity("removed_collaborator", collaborator("user-bob", "Bob"), {
        actorName: "Me",
        actorId: VIEWER,
        currentUserId: VIEWER,
      })
    ).toBe("You removed Bob")
  })

  it("says 'Alice removed you' when the removed person is the viewer", () => {
    expect(
      describeCrossResourceActivity("removed_collaborator", collaborator(VIEWER, "Me"), {
        actorName: "Alice",
        actorId: "user-alice",
        currentUserId: VIEWER,
      })
    ).toBe("Alice removed you")
  })

  it("falls back to 'Removed X' when the actor is unknown", () => {
    expect(
      describeCrossResourceActivity("removed_collaborator", collaborator("user-bob", "Bob"), {
        currentUserId: VIEWER,
      })
    ).toBe("Removed Bob")
  })

  it("falls back to a generic line when neither party is known", () => {
    expect(describeCrossResourceActivity("removed_collaborator", {}, { currentUserId: VIEWER })).toBe(
      "Removed a collaborator"
    )
  })
})

describe("describeCrossResourceActivity: assigned", () => {
  it("substitutes 'You'/'you' for the viewer, keeping the 'to'", () => {
    expect(
      describeCrossResourceActivity("assigned", assignee("user-bob", "Bob"), {
        actorName: "Me",
        actorId: VIEWER,
        currentUserId: VIEWER,
      })
    ).toBe("You assigned to Bob")

    expect(
      describeCrossResourceActivity("assigned", assignee(VIEWER, "Me"), {
        actorName: "Alice",
        actorId: "user-alice",
        currentUserId: VIEWER,
      })
    ).toBe("Alice assigned to you")

    expect(
      describeCrossResourceActivity("assigned", assignee("user-bob", "Bob"), {
        actorName: "Alice",
        actorId: "user-alice",
        currentUserId: VIEWER,
      })
    ).toBe("Alice assigned to Bob")
  })

  it("falls back to 'Assigned to X' (unknown actor) then 'Assigned' (neither)", () => {
    expect(describeCrossResourceActivity("assigned", assignee("user-bob", "Bob"), { currentUserId: VIEWER })).toBe(
      "Assigned to Bob"
    )
    expect(describeCrossResourceActivity("assigned", {}, { currentUserId: VIEWER })).toBe("Assigned")
  })
})

describe("describeCrossResourceActivity: unassigned", () => {
  it("substitutes 'You'/'you' for the viewer", () => {
    expect(
      describeCrossResourceActivity("unassigned", assignee("user-bob", "Bob"), {
        actorName: "Me",
        actorId: VIEWER,
        currentUserId: VIEWER,
      })
    ).toBe("You unassigned Bob")

    expect(
      describeCrossResourceActivity("unassigned", assignee(VIEWER, "Me"), {
        actorName: "Alice",
        actorId: "user-alice",
        currentUserId: VIEWER,
      })
    ).toBe("Alice unassigned you")
  })

  it("falls back to 'Unassigned X' (unknown actor) then 'Unassigned' (neither)", () => {
    expect(describeCrossResourceActivity("unassigned", assignee("user-bob", "Bob"), { currentUserId: VIEWER })).toBe(
      "Unassigned Bob"
    )
    expect(describeCrossResourceActivity("unassigned", {}, { currentUserId: VIEWER })).toBe("Unassigned")
  })
})
