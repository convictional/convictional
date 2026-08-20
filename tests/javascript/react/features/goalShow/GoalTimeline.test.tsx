import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { GoalTimeline } from "../../../../../app/javascript/react/features/goalShow/components/GoalTimeline"
import type { TimelineEvent } from "../../../../../app/javascript/react/features/goalShow/types"
import type { User } from "../../../../../app/javascript/react/shared/types"

afterEach(() => {
  cleanup()
})

// Three update events in chronological order (oldest → newest).
function events(): TimelineEvent[] {
  return ["e-old", "e-mid", "e-new"].map((id, i) => ({
    id,
    action: "goal_update_posted",
    created_at: `2026-01-0${i + 1}T00:00:00Z`,
    creator: { id: "author", display_name: "Author", picture: null },
    details: {},
    owner: null,
    group: null,
    replies: [],
    comment: null,
    goal_update: {
      id: `gu-${id}`,
      question_text: "How's it going?",
      answer_text: `update ${id}`,
      status: "on_track",
      progress: null,
      requested_by: null,
    },
  }))
}

function renderTimeline(lastSeenEventId: string | null) {
  return render(
    <GoalTimeline
      events={events()}
      lastSeenEventId={lastSeenEventId}
      readersByEventId={new Map<string, User[]>()}
    />
  )
}

describe("GoalTimeline New activity divider", () => {
  test("shows the divider when there is activity newer than the last-seen event", () => {
    renderTimeline("e-mid") // e-new is newer → new activity above the line
    expect(screen.queryByText("New activity")).toBeTruthy()
  })

  test("places the divider directly above the first unseen event, not below the last-seen one", () => {
    // Display is newest-first; last-seen is e-mid, so only e-new is unseen. The divider must sit
    // between e-new (unseen, above) and e-mid (last-seen, below) — the off-by-one bug rendered it
    // below e-mid, counting the already-seen e-mid as new.
    const { container } = renderTimeline("e-mid")
    const text = container.textContent ?? ""
    const newIdx = text.indexOf("update e-new")
    const dividerIdx = text.indexOf("New activity")
    const midIdx = text.indexOf("update e-mid")
    expect(newIdx).toBeGreaterThanOrEqual(0)
    expect(dividerIdx).toBeGreaterThan(newIdx)
    expect(midIdx).toBeGreaterThan(dividerIdx)
  })

  test("hides the divider when caught up (last-seen is the newest event)", () => {
    renderTimeline("e-new")
    expect(screen.queryByText("New activity")).toBeNull()
  })

  test("hides the divider when there is no last-seen cursor", () => {
    renderTimeline(null)
    expect(screen.queryByText("New activity")).toBeNull()
  })
})
