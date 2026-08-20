import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { cleanup, screen } from "../../shared/testUtils"
import { renderWithMailboxRouterContext as render } from "./harness"

import { MailboxViewSections } from "../../../../../app/javascript/react/features/mailboxIndex/components/MailboxViewSections"
import type { MailboxMutations } from "../../../../../app/javascript/react/features/mailboxIndex/hooks/useMailboxMutations"
import type { MailboxEntry, ViewSection } from "../../../../../app/javascript/react/features/mailboxIndex/types"

const mutations = {} as unknown as MailboxMutations

function makeEntry(id: string): MailboxEntry {
  return {
    id,
    resource_type: "Chat",
    href: `/chats/${id}`,
    title: `Thread ${id}`,
    preview: null,
    sender_display: null,
    last_activity_at: "2026-05-01T00:00:00Z",
    is_unread: false,
    is_archived: false,
    is_snoozed: false,
    snoozed_until: null,
    is_assigned_to_me: false,
    is_shared: false,
    email: null,
    chat: {
      is_group_chat: false,
      is_dm: true,
      collaborator_count: 2,
      counterparty: { id: "u1", display_name: "Alice", picture: null },
      last_message_author: null,
      member_avatars: [],
      overflow_count: 0,
      last_comment: null,
      last_comment_author_name: null,
    },
    post: null,
    goal: null,
  }
}

function renderSections(sections: ViewSection[], entryIds: string[], isRanked: boolean) {
  const entriesById = Object.fromEntries(entryIds.map(id => [id, makeEntry(id)]))
  return render(
    <MailboxViewSections
      sections={sections}
      entriesById={entriesById}
      mutations={mutations}
      isRanked={isRanked}
      selectedId={null}
      onSelect={vi.fn()}
      onArchiveWithUndo={vi.fn()}
      onSnoozeWithUndo={vi.fn(async () => {})}
      snoozeOpenEntryId={null}
      onSnoozeOpenChange={vi.fn()}
    />
  )
}

const observers: Array<{ callback: IntersectionObserverCallback }> = []

function fireIntersect(visible: boolean): void {
  for (const o of observers) {
    o.callback([{ isIntersecting: visible } as IntersectionObserverEntry], {} as IntersectionObserver)
  }
}

beforeEach(() => {
  observers.length = 0
  vi.stubGlobal(
    "IntersectionObserver",
    vi.fn(function (cb: IntersectionObserverCallback) {
      observers.push({ callback: cb })
      return { observe: vi.fn(), disconnect: vi.fn(), unobserve: vi.fn(), takeRecords: vi.fn() }
    })
  )
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("MailboxViewSections", () => {
  test("renders the load-more sentinel only when there are more entries, and it triggers hydration", () => {
    const onLoadMoreEntries = vi.fn()
    const section: ViewSection = { title: "", description: "", mailbox_entry_ids: ["e1"], goal: null }
    const entriesById = { e1: makeEntry("e1") }
    const props = {
      sections: [section],
      entriesById,
      mutations,
      isRanked: true,
      selectedId: null,
      onSelect: vi.fn(),
      onArchiveWithUndo: vi.fn(),
      onSnoozeWithUndo: vi.fn(async () => {}),
      snoozeOpenEntryId: null,
      onSnoozeOpenChange: vi.fn(),
      onLoadMoreEntries,
    }

    // No sentinel while the full cache is hydrated.
    const { rerender } = render(<MailboxViewSections {...props} hasMoreEntries={false} />)
    expect(observers).toHaveLength(0)

    // More pages remain: the sentinel mounts and hydrates the next page when scrolled into view.
    rerender(<MailboxViewSections {...props} hasMoreEntries={true} />)
    expect(observers).toHaveLength(1)
    fireIntersect(true)
    expect(onLoadMoreEntries).toHaveBeenCalledTimes(1)
  })

  test("grouped renders section header pills and an empty-category placeholder", () => {
    const { container } = renderSections(
      [
        { title: "Work", description: "Job stuff", mailbox_entry_ids: ["e1"], goal: null },
        { title: "Empty", description: "", mailbox_entry_ids: [], goal: null },
      ],
      ["e1"],
      false
    )

    expect(screen.getByText("Work")).toBeInTheDocument()
    expect(screen.getByText("Empty")).toBeInTheDocument()
    expect(screen.getByText("Nothing in this category")).toBeInTheDocument()
    expect(container.querySelectorAll(".view-section").length).toBe(2)
    expect(container.querySelector("#mailbox-entry-e1")).not.toBeNull()
  })

  test("ranked renders one flat list with no section header, GoalBadge, or empty wrapper", () => {
    const { container } = renderSections(
      [{ title: "", description: "", mailbox_entry_ids: ["e2", "e1"], goal: null }],
      ["e1", "e2"],
      true
    )

    // No per-section header chrome — just the rows, in the section's order.
    expect(container.querySelector(".view-section")).toBeNull()
    expect(screen.queryByText("Nothing in this category")).toBeNull()
    const rows = container.querySelectorAll("ul.mailbox-view-entries > li")
    expect(rows.length).toBe(2)
    const order = [...container.querySelectorAll("[data-thread-id]")].map(r => r.getAttribute("data-thread-id"))
    expect(order).toEqual(["e2", "e1"])
  })

  test("ranked with no section yet renders nothing without crashing", () => {
    const { container } = renderSections([], [], true)
    expect(container.querySelector("ul.mailbox-view-entries")?.children.length ?? 0).toBe(0)
  })
})
