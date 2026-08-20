import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

// Drive the data hook directly and stub the heavy toolbar child. The dialog is
// stubbed down to a button that fires onCreate so we can assert the wiring
// without exercising the floating-ui portal here.
vi.mock("~/react/features/meetingsCollectionsIndex/hooks/useCollectionsIndex", () => ({
  useCollectionsIndex: vi.fn(),
}))
vi.mock("~/react/composites/meetings/MeetingsListHeader", () => ({
  MeetingsListHeader: () => <div>list-header</div>,
}))
vi.mock("~/react/features/meetingsCollectionsIndex/components/NewCollectionDialog", () => ({
  NewCollectionDialog: ({
    isOpen,
    onCreate,
  }: {
    isOpen: boolean
    onCreate: (title: string, description: string | null) => Promise<string | null>
  }) =>
    isOpen ? (
      <button type="button" onClick={() => onCreate("New One", null)}>
        dialog-create
      </button>
    ) : null,
}))

import { MeetingsCollectionsIndex } from "~/react/features/meetingsCollectionsIndex/MeetingsCollectionsIndex"
import { useCollectionsIndex } from "~/react/features/meetingsCollectionsIndex/hooks/useCollectionsIndex"

import { makeCollection } from "../../shared/meetingsFixtures"

const mockedHook = vi.mocked(useCollectionsIndex)

function hookValue(overrides: Partial<ReturnType<typeof useCollectionsIndex>> = {}): ReturnType<
  typeof useCollectionsIndex
> {
  return {
    collections: [],
    uncategorizedCount: 0,
    loading: false,
    error: false,
    refresh: vi.fn(),
    create: vi.fn().mockResolvedValue(null),
    ...overrides,
  }
}

beforeEach(() => {
  mockedHook.mockReset()
})

afterEach(cleanup)

describe("MeetingsCollectionsIndex", () => {
  test("renders pseudo rows and real collection rows", () => {
    mockedHook.mockReturnValue(
      hookValue({
        collections: [makeCollection({ id: "a", title: "Weekly Sync" }), makeCollection({ id: "b", title: "Sales" })],
      })
    )
    render(<MeetingsCollectionsIndex />)

    expect(screen.getByText("Most Recent")).toBeInTheDocument()
    expect(screen.getByText("Uncategorized")).toBeInTheDocument()
    expect(screen.getByText("Weekly Sync")).toBeInTheDocument()
    expect(screen.getByText("Sales")).toBeInTheDocument()
  })

  test("shows the uncategorized count badge when there are uncategorized meetings", () => {
    mockedHook.mockReturnValue(hookValue({ uncategorizedCount: 3 }))
    render(<MeetingsCollectionsIndex />)

    expect(screen.getByText("3")).toBeInTheDocument()
  })

  test("the filter narrows both real and pseudo rows", () => {
    mockedHook.mockReturnValue(
      hookValue({
        collections: [makeCollection({ id: "a", title: "Weekly Sync" }), makeCollection({ id: "b", title: "Sales" })],
      })
    )
    render(<MeetingsCollectionsIndex />)

    fireEvent.click(screen.getByLabelText("Filter collections"))
    fireEvent.change(screen.getByPlaceholderText("Filter collections..."), { target: { value: "sales" } })

    expect(screen.getByText("Sales")).toBeInTheDocument()
    expect(screen.queryByText("Weekly Sync")).not.toBeInTheDocument()
    // Pseudo rows are filtered by the same query.
    expect(screen.queryByText("Most Recent")).not.toBeInTheDocument()
  })

  test("shows an empty state when nothing — real or pseudo — matches the filter", () => {
    mockedHook.mockReturnValue(hookValue({ collections: [makeCollection({ id: "a", title: "Weekly Sync" })] }))
    render(<MeetingsCollectionsIndex />)

    fireEvent.click(screen.getByLabelText("Filter collections"))
    fireEvent.change(screen.getByPlaceholderText("Filter collections..."), { target: { value: "zzz" } })

    expect(screen.getByText("No collections match your filter")).toBeInTheDocument()
  })

  test("renders the error state when loading fails", () => {
    mockedHook.mockReturnValue(hookValue({ error: true }))
    render(<MeetingsCollectionsIndex />)

    expect(screen.getByText(/Failed to load collections/i)).toBeInTheDocument()
  })

  test("opening the dialog and creating routes through the hook's create", () => {
    const create = vi.fn().mockResolvedValue(null)
    mockedHook.mockReturnValue(hookValue({ create }))
    render(<MeetingsCollectionsIndex />)

    fireEvent.click(screen.getByRole("button", { name: /New collection/ }))
    fireEvent.click(screen.getByText("dialog-create"))

    expect(create).toHaveBeenCalledWith("New One", null)
  })
})
