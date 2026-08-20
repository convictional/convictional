import { afterEach, describe, expect, test } from "vitest"

import { cleanup, render, screen } from "../../shared/testUtils"
import { PostEntryBody } from "../../../../../app/javascript/react/features/mailboxIndex/components/entryBodies/PostEntryBody"
import type {
  MailboxEntry,
  MailboxEntryListItem,
  PostEntryDetail,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

function makePostEntry(post: PostEntryDetail | null, overrides: Partial<MailboxEntryListItem> = {}): MailboxEntry {
  return {
    id: "p1",
    resource_type: "Post",
    href: "/posts/1?mailbox_entry_id=p1",
    title: "Q3 launch plan",
    preview: null,
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
    post,
    goal: null,
    ...overrides,
  }
}

function postDetail(overrides: Partial<PostEntryDetail> = {}): PostEntryDetail {
  return {
    creator_name: "Grace",
    group_name: null,
    is_announcement: false,
    is_decided: false,
    preview_kind: "activity",
    last_comment: null,
    last_comment_author: null,
    event_action: null,
    event_details: null,
    event_actor: null,
    ...overrides,
  }
}

afterEach(cleanup)

describe("PostEntryBody", () => {
  test("renders a discussion comment as a preview led by the author avatar", () => {
    render(
      <PostEntryBody
        entry={makePostEntry(
          postDetail({
            preview_kind: "comment",
            last_comment: "Looks great — shipping Friday",
            last_comment_author: { id: "u1", display_name: "Ada", picture: null },
          })
        )}
      />
    )
    expect(screen.getByText("Q3 launch plan")).toBeTruthy()
    expect(screen.getByTitle("Ada")).toBeTruthy()
    expect(screen.getByText("Looks great — shipping Friday")).toBeTruthy()
  })

  test("renders the Announcement and Decision chips", () => {
    render(<PostEntryBody entry={makePostEntry(postDetail({ is_announcement: true, is_decided: true }))} />)
    expect(screen.getByText("Announcement")).toBeTruthy()
    expect(screen.getByText("Decision")).toBeTruthy()
  })

  test("renders the creator and group byline", () => {
    render(<PostEntryBody entry={makePostEntry(postDetail({ creator_name: "Grace", group_name: "Platform" }))} />)
    expect(screen.getByText("@Grace")).toBeTruthy()
    expect(screen.getByText("@Platform")).toBeTruthy()
  })

  test("phrases a collaborator-added activity line from actor and details", () => {
    render(
      <PostEntryBody
        entry={makePostEntry(
          postDetail({
            event_action: "added_collaborator",
            event_details: { collaborator: { name: "Ben Franklin" } },
            event_actor: { id: "u2", display_name: "Ada", picture: null },
          })
        )}
      />
    )
    // Activity is a client-phrased line built from the actor + event details.
    expect(screen.getByText("Ada added Ben Franklin")).toBeTruthy()
  })

  test("phrases a state-change activity line from the event action", () => {
    // `decided` is the generic cross-resource action a post decision records (not a post_* action).
    render(<PostEntryBody entry={makePostEntry(postDetail({ event_action: "decided" }))} />)
    expect(screen.getByText("Marked as decided")).toBeTruthy()
  })

  test("renders nothing without post detail", () => {
    const { container } = render(<PostEntryBody entry={makePostEntry(null)} />)
    expect(container.firstChild).toBeNull()
  })
})
