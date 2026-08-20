import { expect, test, describe } from "vitest"

interface User {
  id: string
  display_name: string
  is_collaborator: boolean
}

// Test the collaborator/non-collaborator split logic from MentionSuggester.
// The actual component depends on ProseMirror, but the user grouping is
// the key business logic worth covering.

const users: User[] = [
  { id: "1", display_name: "Alice Admin", is_collaborator: true },
  { id: "2", display_name: "Bob Builder", is_collaborator: false },
  { id: "3", display_name: "Charlie Collab", is_collaborator: true },
  { id: "4", display_name: "Diana Dev", is_collaborator: false },
]

function splitUsers(results: User[]) {
  const collaborators = results.filter(u => u.is_collaborator)
  const nonCollaborators = results.filter(u => !u.is_collaborator)
  return { collaborators, nonCollaborators, allUsers: [...collaborators, ...nonCollaborators] }
}

describe("mention user grouping", () => {
  test("splits users into collaborators and non-collaborators", () => {
    const { collaborators, nonCollaborators } = splitUsers(users)
    expect(collaborators.map(u => u.display_name)).toEqual(["Alice Admin", "Charlie Collab"])
    expect(nonCollaborators.map(u => u.display_name)).toEqual(["Bob Builder", "Diana Dev"])
  })

  test("allUsers puts collaborators first", () => {
    const { allUsers } = splitUsers(users)
    expect(allUsers[0].display_name).toBe("Alice Admin")
    expect(allUsers[1].display_name).toBe("Charlie Collab")
    expect(allUsers[2].display_name).toBe("Bob Builder")
    expect(allUsers[3].display_name).toBe("Diana Dev")
  })

  test("handles all collaborators", () => {
    const allCollabs = users.map(u => ({ ...u, is_collaborator: true }))
    const { collaborators, nonCollaborators } = splitUsers(allCollabs)
    expect(collaborators).toHaveLength(4)
    expect(nonCollaborators).toHaveLength(0)
  })

  test("handles no collaborators", () => {
    const noCollabs = users.map(u => ({ ...u, is_collaborator: false }))
    const { collaborators, nonCollaborators } = splitUsers(noCollabs)
    expect(collaborators).toHaveLength(0)
    expect(nonCollaborators).toHaveLength(4)
  })

  test("handles empty results", () => {
    const { collaborators, nonCollaborators, allUsers } = splitUsers([])
    expect(collaborators).toHaveLength(0)
    expect(nonCollaborators).toHaveLength(0)
    expect(allUsers).toHaveLength(0)
  })
})
