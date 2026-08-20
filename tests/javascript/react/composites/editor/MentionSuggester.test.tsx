import { cleanup, render, screen } from "@testing-library/react"
import { createRef } from "react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { MentionSuggester } from "~/react/composites/editor/components/MentionSuggester"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"

function renderSuggester(results: MentionUser[]) {
  return render(
    <MentionSuggester
      suggesterState={{ shouldShow: true, results, highlightedIndex: 0 }}
      dropdownRef={createRef<HTMLDivElement>()}
      actions={{ select: vi.fn(), dismiss: vi.fn(), setHighlightedIndex: vi.fn() }}
    />
  )
}

afterEach(cleanup)

describe("MentionSuggester section headers", () => {
  test("shows both headers when collaborators and non-collaborators are present", () => {
    renderSuggester([
      { id: "1", display_name: "Alice", is_collaborator: true },
      { id: "2", display_name: "Bob", is_collaborator: false },
    ])
    expect(screen.getByText("Collaborators")).toBeInTheDocument()
    expect(screen.getByText("Invite to collaborate")).toBeInTheDocument()
  })

  test("org-wide context (no collaborators flagged) renders a flat list with no headers", () => {
    renderSuggester([
      { id: "1", display_name: "Alice", is_collaborator: false },
      { id: "2", display_name: "Bob", is_collaborator: false },
    ])
    expect(screen.queryByText("Collaborators")).not.toBeInTheDocument()
    expect(screen.queryByText("Invite to collaborate")).not.toBeInTheDocument()
    // The candidates themselves still render.
    expect(screen.getByText("Alice")).toBeInTheDocument()
    expect(screen.getByText("Bob")).toBeInTheDocument()
  })

  test("collaborators-only (chat) renders a flat list with no headers", () => {
    renderSuggester([
      { id: "1", display_name: "Alice", is_collaborator: true },
      { id: "2", display_name: "Bob", is_collaborator: true },
    ])
    expect(screen.queryByText("Collaborators")).not.toBeInTheDocument()
    expect(screen.queryByText("Invite to collaborate")).not.toBeInTheDocument()
    expect(screen.getByText("Alice")).toBeInTheDocument()
  })
})
