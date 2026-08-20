import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { act, cleanup, fireEvent, render, screen } from "../../shared/testUtils"

import type { Goal } from "~/react/shared/types"

// Capture the editor's onChange so tests can simulate the user typing without
// booting ProseMirror.
const editor = vi.hoisted(() => ({ onChange: null as ((md: string) => void) | null }))

// Stub the whole editor subtree: children include suggester UIs (EmojiSuggester,
// MentionSuggester, LinkTooltip) that read ProseMirror's context via
// useEditorEffect, which the stub can't provide — so don't render them.
vi.mock("~/react/composites/editor/Editor", () => ({
  Editor: () => <div data-testid="editor" />,
  EditorContent: () => <div />,
}))

vi.mock("~/react/composites/editor/features/useViewPlugin", () => ({
  useViewPlugin: ({ onChange }: { onChange: (md: string) => void }) => {
    editor.onChange = onChange
    return { plugins: [], cancel: () => {} }
  },
}))

vi.mock("~/react/shared/apiFetch", () => ({
  // No pending update — the composer stays collapsed until the user opens it.
  apiFetch: vi.fn(() => Promise.resolve(null)),
}))

vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

import { TimelineComposer } from "~/react/features/goalShow/components/TimelineComposer"

const goal = {
  id: "g1",
  owner: { id: "me", display_name: "Me" },
  is_closed: false,
  is_draft: false,
  status: "on_track",
  is_completed: false,
  progress: 0.5,
} as unknown as Goal

// The mocked editor exposes the real onChange; calling it drives the same state
// path keystrokes would.
function type(text: string) {
  act(() => editor.onChange?.(text))
}

function expandComposer() {
  fireEvent.click(screen.getByRole("button", { name: /Share an update/ }))
}

// The "New Update" chip only renders while the composer is expanded, so its
// presence is our proxy for "the form is open" (the form itself lingers in the
// DOM through the close animation, so it can't tell us that on its own).
function isExpanded() {
  return screen.queryByText("New Update") !== null
}

beforeEach(() => {
  editor.onChange = null
})

afterEach(() => {
  cleanup()
})

describe("TimelineComposer update form persistence", () => {
  test("selecting Complete from the status dropdown keeps the composer open", () => {
    render(<TimelineComposer goal={goal} currentUserId="me" noAutoScroll />)
    expandComposer()
    expect(isExpanded()).toBe(true)

    // Open the status dropdown (renders in a floating portal) and pick Complete.
    fireEvent.click(screen.getByRole("button", { name: /On Track/ }))
    const completeItem = screen.getByRole("button", { name: /Complete/ })
    // The mousedown is what used to collapse the form: the menu item lives in a
    // portal outside the composer, so it was mistaken for an "outside" click.
    fireEvent.mouseDown(completeItem)
    fireEvent.click(completeItem)

    // The composer is still open and the status change registered — the trigger
    // now reflects the completed state.
    expect(isExpanded()).toBe(true)
    expect(screen.getByRole("button", { name: /Submit update/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Complete/ })).toBeInTheDocument()
  })

  test("an accidental click outside the form does not discard an in-progress update", () => {
    render(<TimelineComposer goal={goal} currentUserId="me" noAutoScroll />)
    expandComposer()
    type("A long, carefully written update I do not want to lose")

    fireEvent.mouseDown(document.body)

    expect(isExpanded()).toBe(true)
    expect(screen.getByRole("button", { name: /Submit update/ })).toBeInTheDocument()
  })

  test("an outside click still dismisses the composer when nothing has been typed", () => {
    render(<TimelineComposer goal={goal} currentUserId="me" noAutoScroll />)
    expandComposer()
    expect(isExpanded()).toBe(true)

    fireEvent.mouseDown(document.body)

    expect(isExpanded()).toBe(false)
    expect(screen.getByRole("button", { name: /Share an update/ })).toBeInTheDocument()
  })
})
