import { afterEach, beforeEach, describe, expect, test } from "vitest"

import { cleanup, render, screen } from "../../shared/testUtils"
import { resetOrganizationMembers, setOrganizationMembers } from "../../shared/organizationMembersFixtures"
import { GoalEntryBody } from "../../../../../app/javascript/react/features/mailboxIndex/components/entryBodies/GoalEntryBody"
import type {
  MailboxEntry,
  MailboxEntryListItem,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

function makeGoalEntry(overrides: Partial<MailboxEntryListItem> = {}): MailboxEntry {
  return {
    id: "g1",
    resource_type: "Goal",
    href: "/goals/1?mailbox_entry_id=g1",
    title: "Ship Q3",
    preview: "Improve onboarding conversion by 20%",
    sender_display: null,
    last_activity_at: "2026-05-01T00:00:00Z",
    is_unread: true,
    is_archived: false,
    is_snoozed: false,
    snoozed_until: null,
    is_assigned_to_me: false,
    is_shared: true,
    email: null,
    chat: null,
    post: null,
    goal: {
      status: "on_track",
      is_completed: false,
      progress: 0.75,
      preview_kind: "comment",
      last_comment: "Kicking this off",
      last_comment_author: { id: "u1", display_name: "Ada", picture: null },
      event_action: null,
      event_details: null,
      event_actor: null,
    },
    ...overrides,
  }
}

beforeEach(() => {
  setOrganizationMembers({
    users: [{ id: "u9", display_name: "Grace Hopper", picture: null }],
    groups: [{ id: "grp1", name: "Platform" }],
  })
})

afterEach(() => {
  cleanup()
  resetOrganizationMembers()
})

describe("GoalEntryBody", () => {
  test("renders a comment in a chip bubble with the author avatar", () => {
    render(<GoalEntryBody entry={makeGoalEntry()} />)
    expect(screen.getByText("Ship Q3")).toBeTruthy()
    expect(screen.getByText("On Track")).toBeTruthy()
    // Progress renders as the shared pie widget, labelled with the percentage.
    expect(screen.getByLabelText("75% complete")).toBeTruthy()
    expect(screen.getByText("Kicking this off").closest(".rounded-full")).not.toBeNull()
    // The description lives in a hover tooltip, so it is not rendered inline.
    expect(screen.queryByText("Improve onboarding conversion by 20%")).toBeNull()
  })

  test("renders a posted update as plain text (no chip)", () => {
    render(
      <GoalEntryBody
        entry={makeGoalEntry({
          goal: {
            status: "at_risk",
            is_completed: false,
            progress: 0.7,
            preview_kind: "update",
            last_comment: "The goal is coming along, but we are still a ways off",
            last_comment_author: { id: "u2", display_name: "Grace", picture: null },
            event_action: null,
            event_details: null,
            event_actor: null,
          },
        })}
      />
    )
    const text = screen.getByText("The goal is coming along, but we are still a ways off")
    expect(text).toBeTruthy()
    expect(text.closest(".rounded-full")).toBeNull()
  })

  test("phrases an activity summary from the event, as a plain line with no author", () => {
    render(
      <GoalEntryBody
        entry={makeGoalEntry({
          goal: {
            status: "off_track",
            is_completed: false,
            progress: null,
            preview_kind: "activity",
            last_comment: null,
            last_comment_author: null,
            event_action: "goal_updated",
            event_details: { status: ["on_track", "off_track"] },
            event_actor: null,
          },
        })}
      />
    )
    // The status chip and the phrased line both read "Off Track", so scope to the summary line.
    expect(screen.getByText("Status changed to Off Track").closest(".rounded-full")).toBeNull()
  })

  test("resolves owner and group ids to names from the org-members cache", () => {
    render(
      <GoalEntryBody
        entry={makeGoalEntry({
          goal: {
            status: "on_track",
            is_completed: false,
            progress: null,
            preview_kind: "activity",
            last_comment: null,
            last_comment_author: null,
            event_action: "goal_updated",
            event_details: { owner_id: [null, "u9"] },
            event_actor: null,
          },
        })}
      />
    )
    expect(screen.getByText("Owner changed to Grace Hopper")).toBeTruthy()
  })

  test("falls back to a generic phrase when the id is not cached", () => {
    render(
      <GoalEntryBody
        entry={makeGoalEntry({
          goal: {
            status: "on_track",
            is_completed: false,
            progress: null,
            preview_kind: "activity",
            last_comment: null,
            last_comment_author: null,
            event_action: "goal_updated",
            event_details: { group_id: [null, "unknown"] },
            event_actor: null,
          },
        })}
      />
    )
    expect(screen.getByText("Group changed")).toBeTruthy()
  })

  test("renders a due-date change with the date through UserDateTime", () => {
    render(
      <GoalEntryBody
        entry={makeGoalEntry({
          goal: {
            status: "on_track",
            is_completed: false,
            progress: null,
            preview_kind: "activity",
            last_comment: null,
            last_comment_author: null,
            event_action: "goal_updated",
            event_details: { target_date: [null, "2026-07-15"] },
            event_actor: null,
          },
        })}
      />
    )
    expect(screen.getByText("Due date changed to")).toBeTruthy()
    expect(screen.getByText("Jul 15 2026")).toBeTruthy()
  })

  test("renders a cleared due date without a trailing date", () => {
    render(
      <GoalEntryBody
        entry={makeGoalEntry({
          goal: {
            status: "on_track",
            is_completed: false,
            progress: null,
            preview_kind: "activity",
            last_comment: null,
            last_comment_author: null,
            event_action: "goal_updated",
            event_details: { target_date: ["2026-07-15", null] },
            event_actor: null,
          },
        })}
      />
    )
    expect(screen.getByText("Due date changed")).toBeTruthy()
    expect(screen.queryByText("Jul 15 2026")).toBeNull()
  })

  test("phrases an update request from the actor and question", () => {
    render(
      <GoalEntryBody
        entry={makeGoalEntry({
          goal: {
            status: "on_track",
            is_completed: false,
            progress: 0.5,
            preview_kind: "activity",
            last_comment: null,
            last_comment_author: null,
            event_action: "goal_update_requested",
            event_details: { question_text: "Where are we?" },
            event_actor: { id: "u3", display_name: "Ada", picture: null },
          },
        })}
      />
    )
    expect(screen.getByText("Update requested from Ada - Where are we?")).toBeTruthy()
  })

  test("renders a completion badge for a completed goal", () => {
    render(
      <GoalEntryBody
        entry={makeGoalEntry({
          goal: {
            status: "on_track",
            is_completed: true,
            progress: 1,
            preview_kind: "activity",
            last_comment: null,
            last_comment_author: null,
            event_action: "goal_completed",
            event_details: null,
            event_actor: null,
          },
        })}
      />
    )
    expect(screen.getByText("Complete")).toBeTruthy()
    expect(screen.getByLabelText("100% complete")).toBeTruthy()
  })

  test("renders nothing without goal detail", () => {
    const { container } = render(<GoalEntryBody entry={makeGoalEntry({ goal: null })} />)
    expect(container.firstChild).toBeNull()
  })
})
