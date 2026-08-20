import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type {
  MailboxEntry,
  MailboxEntryListItem,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

vi.mock("../../../../../app/javascript/react/features/mailboxIndex/components/EntryRow", () => ({
  EntryRow: ({ entry }: { entry: MailboxEntry }) => (
    <li data-testid="entry-row" data-entry-id={entry.id}>
      {entry.title}
    </li>
  ),
}))

vi.mock("../../../../../app/javascript/react/features/mailboxIndex/components/GoalsSpotlight", () => ({
  GoalsSpotlight: () => null,
}))

import { EntryList } from "../../../../../app/javascript/react/features/mailboxIndex/components/EntryList"
import type { MailboxMutations } from "../../../../../app/javascript/react/features/mailboxIndex/hooks/useMailboxEntries"

function makeEntry(overrides: Partial<MailboxEntryListItem> = {}): MailboxEntry {
  return {
    id: "e1",
    resource_type: "Chat",
    href: "/chats/1",
    title: "Test thread",
    preview: null,
    sender_display: null,
    last_activity_at: "2026-05-01T00:00:00Z",
    is_unread: true,
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
      counterparty: null,
      last_message_author: null,
      member_avatars: [],
      overflow_count: 0,
      last_comment: null,
      last_comment_author_name: null,
    },
    post: null,
    goal: null,
    ...overrides,
  }
}

const noopMutations: MailboxMutations = {
  archive: async () => {},
  unarchive: async () => {},
  markRead: async () => {},
  markUnread: async () => {},
  snooze: async () => {},
  unsnooze: async () => {},
}

function renderList(props: Partial<React.ComponentProps<typeof EntryList>> = {}) {
  return render(
    <EntryList
      entries={[]}
      view="inbox"
      isMobile={false}
      selectedId={null}
      hasMore={false}
      hasLoadedMore={false}
      loading={false}
      loadingMore={false}
      onLoadMore={() => {}}
      onReturnToTop={() => {}}
      onSelect={() => {}}
      mutations={noopMutations}
      onArchiveWithUndo={() => {}}
      onSnoozeWithUndo={async () => {}}
      snoozeOpenEntryId={null}
      onSnoozeOpenChange={() => {}}
      {...props}
    />
  )
}

afterEach(() => {
  cleanup()
})

describe("EntryList", () => {
  test("shows skeleton when loading with no entries", () => {
    renderList({ loading: true, entries: [] })
    expect(screen.getByTestId("entry-list-skeleton")).toBeTruthy()
    expect(screen.queryAllByTestId("entry-row")).toHaveLength(0)
  })

  test("keeps populated rows visible during a background refetch", () => {
    const entry = makeEntry()
    const { container } = renderList({ loading: true, entries: [entry] })

    // The spinner-only branch must not fire when entries already exist —
    // otherwise the inbox briefly blanks during reconnects or scroll-to-top
    // resets.
    const rows = screen.getAllByTestId("entry-row")
    expect(rows).toHaveLength(1)
    expect(rows[0].getAttribute("data-entry-id")).toBe("e1")
    expect(container.querySelector(".loading-spinner")).toBeNull()
  })

  test("shows empty state when not loading and no entries", () => {
    renderList({ loading: false, entries: [], view: "inbox" })
    expect(screen.getByText("Inbox zero")).toBeTruthy()
  })
})

describe("EntryList top-of-list reconcile", () => {
  interface FakeObserver {
    cb: IntersectionObserverCallback
    connected: boolean
  }
  const observers: FakeObserver[] = []

  // Drive every live top-marker observer with an intersection state.
  function fireTop(visible: boolean): void {
    for (const o of observers) {
      if (o.connected) o.cb([{ isIntersecting: visible } as IntersectionObserverEntry], {} as IntersectionObserver)
    }
  }

  beforeEach(() => {
    observers.length = 0
    vi.stubGlobal(
      "IntersectionObserver",
      vi.fn(function (cb: IntersectionObserverCallback) {
        const observer: FakeObserver = { cb, connected: true }
        observers.push(observer)
        return {
          observe: vi.fn(),
          disconnect: vi.fn(() => {
            observer.connected = false
          }),
          unobserve: vi.fn(),
          takeRecords: vi.fn(),
        }
      })
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test("does not reconcile while the top stays in view (no collapse↔refill loop)", () => {
    const onReturnToTop = vi.fn()
    renderList({ entries: [makeEntry()], hasLoadedMore: true, onReturnToTop })
    // Whole list fits on screen: the top marker is continuously visible and never
    // leaves. Repeated "visible" callbacks must not reconcile — otherwise a
    // collapse-to-page-1 gets refilled by the bottom sentinel and reconciled forever.
    fireTop(true)
    fireTop(true)
    expect(onReturnToTop).not.toHaveBeenCalled()
  })

  test("reconciles once per genuine return to the top", () => {
    const onReturnToTop = vi.fn()
    renderList({ entries: [makeEntry()], hasLoadedMore: true, onReturnToTop })
    fireTop(false) // scrolled down into the frozen tail
    fireTop(true) // ...and came back
    expect(onReturnToTop).toHaveBeenCalledTimes(1)
    // Still at the top: no further reconcile until the marker leaves and returns again.
    fireTop(true)
    expect(onReturnToTop).toHaveBeenCalledTimes(1)
    fireTop(false)
    fireTop(true)
    expect(onReturnToTop).toHaveBeenCalledTimes(2)
  })

  test("does not observe the top until a tail is loaded", () => {
    renderList({ entries: [makeEntry()], hasLoadedMore: false })
    expect(globalThis.IntersectionObserver).not.toHaveBeenCalled()
  })
})
