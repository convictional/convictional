import { afterEach, describe, expect, test, vi } from "vitest"

import { SearchablePicker } from "~/react/composites/SearchablePicker"

import { cleanup, fireEvent, render, screen } from "../shared/testUtils"

interface Item {
  id: string
  name: string
}

const ITEMS: Item[] = [
  { id: "a", name: "Alpha" },
  { id: "b", name: "Bravo" },
  { id: "c", name: "Charlie" },
]

// Renders the picker with a plain <button> trigger and simple item rows. Each
// row is a <button> that calls the shared onSelect spy (with the item's name)
// and then closes the panel — this is how we assert selection closes the picker.
function renderPicker(overrides: Partial<Parameters<typeof SearchablePicker<Item>>[0]> = {}) {
  const onSelect = vi.fn()
  const props = {
    trigger: <button type="button">Open picker</button>,
    title: "Pick an item",
    items: ITEMS,
    getKey: (item: Item) => item.id,
    getSearchText: (item: Item) => item.name,
    renderItem: (item: Item, close: () => void) => (
      <button
        type="button"
        onClick={() => {
          onSelect(item.name)
          close()
        }}
      >
        {item.name}
      </button>
    ),
    renderHeader: () => <div>Header marker</div>,
    renderFooter: () => <div>Footer marker</div>,
    searchPlaceholder: "Search items",
    ...overrides,
  } as Parameters<typeof SearchablePicker<Item>>[0]

  const utils = render(<SearchablePicker<Item> {...props} />)
  return { ...utils, onSelect }
}

afterEach(() => {
  cleanup()
  delete document.documentElement.dataset.isMobile
})

describe("SearchablePicker (desktop dropdown)", () => {
  test("opens on trigger click, filters items case-insensitively, and selection closes it", () => {
    const { onSelect } = renderPicker()

    // Closed: nothing from the panel is in the DOM yet.
    expect(screen.queryByPlaceholderText("Search items")).toBeNull()

    // Click the trigger to open the floating panel.
    fireEvent.click(screen.getByText("Open picker"))

    // Open: search input, pinned header/footer, and every item row are shown.
    const search = screen.getByPlaceholderText("Search items")
    expect(search).toBeInTheDocument()
    expect(screen.getByText("Header marker")).toBeInTheDocument()
    expect(screen.getByText("Footer marker")).toBeInTheDocument()
    expect(screen.getByText("Alpha")).toBeInTheDocument()
    expect(screen.getByText("Bravo")).toBeInTheDocument()
    expect(screen.getByText("Charlie")).toBeInTheDocument()

    // Typing filters the item rows case-insensitively; header/footer stay put.
    fireEvent.change(search, { target: { value: "br" } })
    expect(screen.getByText("Bravo")).toBeInTheDocument()
    expect(screen.queryByText("Alpha")).toBeNull()
    expect(screen.queryByText("Charlie")).toBeNull()
    expect(screen.getByText("Header marker")).toBeInTheDocument()
    expect(screen.getByText("Footer marker")).toBeInTheDocument()

    // A query matching no item shows the default empty-state row.
    fireEvent.change(search, { target: { value: "zzz" } })
    expect(screen.getByText("No results match your search")).toBeInTheDocument()
    expect(screen.queryByText("Bravo")).toBeNull()

    // Clearing the query restores the full list, then selecting a row calls the
    // handler and closes the panel (the search input disappears).
    fireEvent.change(search, { target: { value: "" } })
    fireEvent.click(screen.getByText("Charlie"))
    expect(onSelect).toHaveBeenCalledWith("Charlie")
    expect(screen.queryByPlaceholderText("Search items")).toBeNull()
  })

  test("hides the search input when there are no items but still shows header/footer", () => {
    renderPicker({ items: [] })

    fireEvent.click(screen.getByText("Open picker"))

    expect(screen.queryByPlaceholderText("Search items")).toBeNull()
    expect(screen.queryByText("No results match your search")).toBeNull()
    expect(screen.getByText("Header marker")).toBeInTheDocument()
    expect(screen.getByText("Footer marker")).toBeInTheDocument()
  })

  test("renders a Loading… row in place of items/empty-state when loading", () => {
    renderPicker({ loading: true })

    fireEvent.click(screen.getByText("Open picker"))

    // The search input is present (items.length > 0 || loading), but the rows
    // and empty-state give way to a single loading indicator.
    expect(screen.getByPlaceholderText("Search items")).toBeInTheDocument()
    expect(screen.getByText("Loading…")).toBeInTheDocument()
    expect(screen.queryByText("Alpha")).toBeNull()
    expect(screen.queryByText("No results match your search")).toBeNull()
  })
})

describe("SearchablePicker (mobile bottom sheet)", () => {
  test("opens a titled dialog with search + rows and selecting a row calls the handler", () => {
    // The server publishes UA-derived mobile state on <html>; useIsMobile reads it.
    document.documentElement.dataset.isMobile = "true"

    const { onSelect } = renderPicker()

    fireEvent.click(screen.getByText("Open picker"))

    // Mobile renders a BottomSheet, which is a role="dialog" labelled by `title`.
    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveTextContent("Pick an item")
    expect(screen.getByPlaceholderText("Search items")).toBeInTheDocument()
    expect(screen.getByText("Alpha")).toBeInTheDocument()
    expect(screen.getByText("Bravo")).toBeInTheDocument()

    // Selecting a row invokes the handler. (The sheet's close animation is native
    // animationend-driven, so we don't assert it finishes unmounting here.)
    fireEvent.click(screen.getByText("Bravo"))
    expect(onSelect).toHaveBeenCalledWith("Bravo")
  })
})
