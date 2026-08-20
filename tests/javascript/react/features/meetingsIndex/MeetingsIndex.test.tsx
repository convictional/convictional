import { cleanup, render, screen } from "../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

// Drive the data hook directly and stub the children down to markers so these
// tests exercise only the header-region selection and the
// loading/error/empty/ready state gate.
vi.mock("~/react/features/meetingsIndex/hooks/useMeetingsIndex", () => ({
  useMeetingsIndex: vi.fn(),
}))
vi.mock("~/react/composites/meetings/MeetingsListHeader", () => ({
  MeetingsListHeader: () => <div>list-header</div>,
}))
vi.mock("~/react/composites/meetings/MeetingCard", () => ({
  MeetingCard: ({ meeting }: { meeting: { id: string } }) => <div>meeting-card-{meeting.id}</div>,
}))
vi.mock("~/react/features/meetingsIndex/components/CollectionHeader", () => ({
  CollectionHeader: ({ collection }: { collection: { title: string } }) => <div>header-{collection.title}</div>,
}))
vi.mock("~/react/ui/LoadMoreSentinel", () => ({
  LoadMoreSentinel: () => <div>load-more</div>,
}))

import { MeetingsIndex } from "~/react/features/meetingsIndex/MeetingsIndex"
import { useMeetingsIndex } from "~/react/features/meetingsIndex/hooks/useMeetingsIndex"

import { makeCollection, makeMeeting } from "../../shared/meetingsFixtures"
import { resetCurrentUser, setCurrentUser } from "../../shared/currentUserFixtures"

const mockedHook = vi.mocked(useMeetingsIndex)

function hookValue(overrides: Partial<ReturnType<typeof useMeetingsIndex>> = {}): ReturnType<typeof useMeetingsIndex> {
  return {
    collection: null,
    meetings: [],
    loading: false,
    loadingMore: false,
    error: false,
    hasMore: false,
    loadMore: vi.fn(),
    upsertMeeting: vi.fn(),
    updateCollection: vi.fn(),
    deleteCollection: vi.fn(),
    ...overrides,
  }
}

const collectionProps = { collectionId: "col-1", uncategorized: false, collectionsIndexUrl: "/meetings_collections" }
const mostRecentProps = { collectionId: null, uncategorized: false, collectionsIndexUrl: "/meetings_collections" }
const uncategorizedProps = { collectionId: null, uncategorized: true, collectionsIndexUrl: "/meetings_collections" }

beforeEach(() => {
  mockedHook.mockReset()
  setCurrentUser({ id: "u1", time_zone: "UTC" })
})

afterEach(() => {
  cleanup()
  resetCurrentUser()
})

describe("MeetingsIndex collection mode", () => {
  test("shows the loading state without a header before the collection arrives", () => {
    mockedHook.mockReturnValue(hookValue({ loading: true, collection: null }))
    render(<MeetingsIndex {...collectionProps} />)

    expect(screen.queryByText(/^header-/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Failed to load/i)).not.toBeInTheDocument()
  })

  test("shows the error state when loading fails", () => {
    mockedHook.mockReturnValue(hookValue({ error: true, collection: null }))
    render(<MeetingsIndex {...collectionProps} />)

    expect(screen.getByText(/Failed to load this collection/i)).toBeInTheDocument()
  })

  test("renders the collection header and an empty state when it has no meetings", () => {
    mockedHook.mockReturnValue(hookValue({ collection: makeCollection({ title: "Weekly Sync" }), meetings: [] }))
    render(<MeetingsIndex {...collectionProps} />)

    expect(screen.getByText("header-Weekly Sync")).toBeInTheDocument()
    expect(screen.getByText(/no recordings in this collection/i)).toBeInTheDocument()
  })

  test("renders meeting cards and the load-more sentinel only when there is more", () => {
    mockedHook.mockReturnValue(
      hookValue({
        collection: makeCollection({ title: "Weekly Sync" }),
        meetings: [makeMeeting({ id: "a" }), makeMeeting({ id: "b" })],
        hasMore: true,
      })
    )
    render(<MeetingsIndex {...collectionProps} />)

    expect(screen.getByText("meeting-card-a")).toBeInTheDocument()
    expect(screen.getByText("meeting-card-b")).toBeInTheDocument()
    expect(screen.getByText("load-more")).toBeInTheDocument()
  })

  test("omits the load-more sentinel and shows the end marker when there is no more", () => {
    mockedHook.mockReturnValue(
      hookValue({ collection: makeCollection(), meetings: [makeMeeting({ id: "a" })], hasMore: false })
    )
    render(<MeetingsIndex {...collectionProps} />)

    expect(screen.queryByText("load-more")).not.toBeInTheDocument()
    expect(screen.getByText("No more meetings")).toBeInTheDocument()
  })
})

describe("MeetingsIndex pseudo-collection mode", () => {
  test("renders the Most Recent header and never a collection header", () => {
    mockedHook.mockReturnValue(hookValue({ meetings: [makeMeeting({ id: "a" })] }))
    render(<MeetingsIndex {...mostRecentProps} />)

    expect(screen.getByText("Most Recent")).toBeInTheDocument()
    expect(screen.getByText(/recordings you were an attendee of/i)).toBeInTheDocument()
    expect(screen.queryByText(/^header-/)).not.toBeInTheDocument()
  })

  test("renders the Uncategorized header and description", () => {
    mockedHook.mockReturnValue(hookValue({ meetings: [] }))
    render(<MeetingsIndex {...uncategorizedProps} />)

    expect(screen.getByText("Uncategorized")).toBeInTheDocument()
    expect(screen.getByText(/not in any other collection/i)).toBeInTheDocument()
  })

  test("keeps the static header visible while loading and on error", () => {
    mockedHook.mockReturnValue(hookValue({ error: true }))
    render(<MeetingsIndex {...mostRecentProps} />)

    expect(screen.getByText("Most Recent")).toBeInTheDocument()
    expect(screen.getByText(/Failed to load meetings/i)).toBeInTheDocument()
  })
})
