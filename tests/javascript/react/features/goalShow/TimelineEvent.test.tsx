import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { TimelineEventRenderer } from "../../../../../app/javascript/react/features/goalShow/components/TimelineEvent"
import type { TimelineEvent } from "../../../../../app/javascript/react/features/goalShow/types"

afterEach(() => {
  cleanup()
})

function makeEvent(overrides: Partial<TimelineEvent> = {}): TimelineEvent {
  return {
    id: "evt-1",
    action: "goal_created",
    created_at: "2026-01-01T00:00:00Z",
    creator: { id: "user-1", display_name: "Alice", picture: null },
    details: {},
    owner: null,
    group: null,
    replies: [],
    comment: null,
    goal_update: null,
    ...overrides,
  }
}

describe("TimelineEventRenderer", () => {
  test("renders lifecycle events with correct labels", () => {
    const cases: [string, string][] = [
      ["goal_created", "Goal created"],
      ["goal_completed", "Goal completed"],
      ["goal_closed", "Goal closed"],
      ["goal_reactivated", "Goal reopened"],
      ["goal_activated", "Goal reactivated"],
      ["goal_deleted", "Goal deleted"],
    ]

    for (const [action, label] of cases) {
      cleanup()
      render(<TimelineEventRenderer event={makeEvent({ action })} />)
      expect(screen.getByText(label)).toBeTruthy()
      expect(screen.getByText("by Alice")).toBeTruthy()
    }
  })

  test("returns nothing for unknown event actions", () => {
    const { container } = render(<TimelineEventRenderer event={makeEvent({ action: "unknown_action" })} />)
    expect(container.innerHTML).toBe("")
  })

  test("goal_updated with no describable changes renders nothing", () => {
    const { container } = render(
      <TimelineEventRenderer event={makeEvent({ action: "goal_updated", details: {} })} />
    )
    expect(container.querySelector("#goal-event-evt-1")?.innerHTML).toBe("")
  })

  test("goal_updated with status change shows formatted status", () => {
    render(
      <TimelineEventRenderer
        event={makeEvent({
          action: "goal_updated",
          details: { status: ["on_track", "at_risk"] },
        })}
      />
    )
    expect(screen.getByText("At Risk")).toBeTruthy()
  })

  test("goal_updated with title change shows new title", () => {
    render(
      <TimelineEventRenderer
        event={makeEvent({
          action: "goal_updated",
          details: { title: ["Old Title", "New Title"] },
        })}
      />
    )
    expect(screen.getByText("New Title")).toBeTruthy()
  })

  test("goal_updated with owner change shows owner name", () => {
    render(
      <TimelineEventRenderer
        event={makeEvent({
          action: "goal_updated",
          details: { owner_id: [null, "user-2"] },
          owner: { id: "user-2", display_name: "Bob", picture: null },
        })}
      />
    )
    expect(screen.getByText("Bob")).toBeTruthy()
  })

  test("goal_updated with multiple changes renders list", () => {
    render(
      <TimelineEventRenderer
        event={makeEvent({
          action: "goal_updated",
          details: {
            status: ["on_track", "off_track"],
            title: ["Old", "New"],
          },
        })}
      />
    )
    expect(screen.getByText("Goal updated")).toBeTruthy()
    expect(screen.getByText("Off Track")).toBeTruthy()
    expect(screen.getByText("New")).toBeTruthy()
  })

  test("goal_update_posted renders update card with question and answer", () => {
    render(
      <TimelineEventRenderer
        event={makeEvent({
          action: "goal_update_posted",
          goal_update: {
            id: "gu-1",
            question_text: "How's it going?",
            answer_text: "Making progress",
            status: "on_track",
            progress: 0.75,
            requested_by: null,
          },
        })}
      />
    )
    expect(screen.getByText("Update")).toBeTruthy()
    expect(screen.getByText("How's it going?")).toBeTruthy()
    expect(screen.getByText("Making progress")).toBeTruthy()
  })

  test("goal_update_posted shows who requested the update", () => {
    render(
      <TimelineEventRenderer
        event={makeEvent({
          action: "goal_update_posted",
          goal_update: {
            id: "gu-1",
            question_text: "Status?",
            answer_text: "Done",
            status: "on_track",
            progress: null,
            requested_by: { id: "user-2", display_name: "Bob", picture: null },
          },
        })}
      />
    )
    expect(screen.getByText("Responding to Bob")).toBeTruthy()
  })

  test("goal_commented renders comment content and replies", () => {
    render(
      <TimelineEventRenderer
        event={makeEvent({
          action: "goal_commented",
          comment: {
            id: "c-1",
            content: "Looks good!",
            user: { id: "user-1", display_name: "Alice", picture: null },
          },
          replies: [
            makeEvent({
              id: "evt-reply",
              action: "goal_commented",
              comment: {
                id: "c-2",
                content: "Thanks!",
                user: { id: "user-2", display_name: "Bob", picture: null },
              },
            }),
          ],
        })}
      />
    )
    expect(screen.getByText("Looks good!")).toBeTruthy()
    expect(screen.getByText("Thanks!")).toBeTruthy()
  })
})
