import { afterEach, beforeEach, describe, expect, test } from "vitest"

import { resetCurrentUser, setCurrentUser } from "../../shared/currentUserFixtures"
import { cleanup, render, screen } from "../../shared/testUtils"
import { EmailThreadEntryBody } from "../../../../../app/javascript/react/features/mailboxIndex/components/entryBodies/EmailThreadEntryBody"
import type {
  EmailEntryDetail,
  MailboxEntry,
  MailboxEntryListItem,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

function makeEmailEntry(email: EmailEntryDetail | null, overrides: Partial<MailboxEntryListItem> = {}): MailboxEntry {
  return {
    id: "e1",
    resource_type: "EmailThread",
    href: "/email_threads/1?mailbox_entry_id=e1",
    title: "Q3 planning",
    preview: "Here is the latest draft of the plan",
    sender_display: null,
    last_activity_at: "2026-05-01T00:00:00Z",
    is_unread: true,
    is_archived: false,
    is_snoozed: false,
    snoozed_until: null,
    is_assigned_to_me: false,
    is_shared: false,
    email,
    chat: null,
    post: null,
    goal: null,
    ...overrides,
  }
}

function emailDetail(overrides: Partial<EmailEntryDetail> = {}): EmailEntryDetail {
  return {
    sender_display: "Ada Lovelace",
    message_count: 3,
    attachment_count: 0,
    preview_kind: "message",
    last_comment: null,
    last_comment_author: null,
    event_action: null,
    event_details: null,
    event_actor: null,
    scheduled_for: null,
    ...overrides,
  }
}

// The scheduled-draft badge is behind a superuser launch gate; seed a superuser
// viewer so the badge renders, and reset between tests.
beforeEach(() => setCurrentUser({ id: "u1", is_superuser: true }))
afterEach(() => {
  cleanup()
  resetCurrentUser()
})

describe("EmailThreadEntryBody", () => {
  test("renders the message snippet for a message preview", () => {
    render(<EmailThreadEntryBody entry={makeEmailEntry(emailDetail())} />)
    expect(screen.getByText("Ada Lovelace")).toBeTruthy()
    expect(screen.getByText("Here is the latest draft of the plan")).toBeTruthy()
  })

  test("renders a comment as a chip led by the author avatar", () => {
    render(
      <EmailThreadEntryBody
        entry={makeEmailEntry(
          emailDetail({
            preview_kind: "comment",
            last_comment: "Can we push the deadline?",
            last_comment_author: { id: "u1", display_name: "Grace", picture: null },
          })
        )}
      />
    )
    expect(screen.getByTitle("Grace")).toBeTruthy()
    expect(screen.getByText("Can we push the deadline?")).toBeTruthy()
  })

  test("phrases a collaborator-added activity line from actor and details", () => {
    render(
      <EmailThreadEntryBody
        entry={makeEmailEntry(
          emailDetail({
            preview_kind: "activity",
            event_action: "added_collaborator",
            event_details: { collaborator: { name: "Ben Franklin" } },
            event_actor: { id: "u2", display_name: "Ada", picture: null },
          })
        )}
      />
    )
    expect(screen.getByText("Ada added Ben Franklin")).toBeTruthy()
  })

  test("phrases a decided activity line from the event action", () => {
    render(
      <EmailThreadEntryBody
        entry={makeEmailEntry(emailDetail({ preview_kind: "activity", event_action: "decided" }))}
      />
    )
    expect(screen.getByText("Marked as decided")).toBeTruthy()
  })

  test("marks a scheduled draft with a schedule badge, and omits it otherwise", () => {
    const { rerender } = render(
      <EmailThreadEntryBody entry={makeEmailEntry(emailDetail({ scheduled_for: "2026-05-04T13:00:00Z" }))} />
    )
    expect(screen.getByText("schedule_send")).toBeTruthy()

    rerender(<EmailThreadEntryBody entry={makeEmailEntry(emailDetail({ scheduled_for: null }))} />)
    expect(screen.queryByText("schedule_send")).toBeNull()
  })

  test("hides the schedule badge from non-superusers (launch gate)", () => {
    setCurrentUser({ id: "u1", is_superuser: false })
    render(<EmailThreadEntryBody entry={makeEmailEntry(emailDetail({ scheduled_for: "2026-05-04T13:00:00Z" }))} />)
    expect(screen.queryByText("schedule_send")).toBeNull()
  })

  test("keeps the draft snippet for a scheduled draft instead of a 'scheduled' line", () => {
    render(
      <EmailThreadEntryBody
        entry={makeEmailEntry(
          emailDetail({
            preview_kind: "activity",
            event_action: "draft_scheduled",
            event_actor: { id: "u2", display_name: "Ada", picture: null },
            scheduled_for: "2026-05-04T13:00:00Z",
          })
        )}
      />
    )
    expect(screen.getByText("Here is the latest draft of the plan")).toBeTruthy()
    expect(screen.queryByText(/scheduled a draft/i)).toBeNull()
    // The scheduled badge (top row) still renders.
    expect(screen.getByText("schedule_send")).toBeTruthy()
  })

  test("renders nothing without email detail", () => {
    const { container } = render(<EmailThreadEntryBody entry={makeEmailEntry(null)} />)
    expect(container.firstChild).toBeNull()
  })
})
