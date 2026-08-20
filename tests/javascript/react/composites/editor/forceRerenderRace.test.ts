import { renderHook, waitFor } from "@testing-library/react"
import { EditorState } from "prosemirror-state"
import { EditorView } from "prosemirror-view"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { prosemirrorToYXmlFragment } from "y-prosemirror"
import * as Y from "yjs"

// Track every IndexeddbPersistence we construct so the test can resolve their
// whenSynced promises and capture their ydoc reference.
interface FakeIdbPersistence {
  whenSynced: Promise<void>
  resolveSynced: () => void
  destroy: () => void
}
const idbPersistences: FakeIdbPersistence[] = []

// Capture the ydoc that ChannelsYjsProvider receives so the test can populate
// yXmlFragment after useCollaboration's session has been built — simulating
// IndexedDB load or network sync arriving between session creation and
// EditorView mount.
let capturedYdoc: Y.Doc | null = null

vi.mock("y-indexeddb", () => ({
  IndexeddbPersistence: vi.fn().mockImplementation(function () {
    let resolveSynced!: () => void
    const whenSynced = new Promise<void>(resolve => {
      resolveSynced = resolve
    })
    const instance: FakeIdbPersistence = { whenSynced, resolveSynced, destroy: vi.fn() }
    idbPersistences.push(instance)
    return instance
  }),
}))

vi.mock("~/channels/yjsProvider", async () => {
  const { ObservableV2 } = await vi.importActual<typeof import("lib0/observable")>("lib0/observable")
  const { Awareness } = await vi.importActual<typeof import("y-protocols/awareness")>("y-protocols/awareness")
  class FakeProvider extends (ObservableV2 as unknown as new () => {
    emit: (event: string, args: unknown[]) => void
    on: (event: string, cb: (...args: unknown[]) => void) => void
    off: (event: string, cb: (...args: unknown[]) => void) => void
  }) {
    public awareness: InstanceType<typeof Awareness>
    constructor(_client: unknown, _stream: string, _params: Record<string, string>, ydoc: Y.Doc) {
      super()
      capturedYdoc = ydoc
      // yCursorPlugin reads awareness.on(...) during view construction, so use
      // the real Awareness implementation rather than a stub.
      this.awareness = new Awareness(ydoc)
    }
    destroy(): void {
      this.awareness.destroy()
    }
  }
  return { ChannelsYjsProvider: FakeProvider }
})

import { useCollaboration } from "~/react/composites/editor/features/useCollaboration"
import { parse, schema } from "~/richText/schema"
import type { ChannelsClient } from "~/channels/client"

const fakeChannelsClient = { on: vi.fn(), off: vi.fn() } as unknown as ChannelsClient
const currentUser = { id: "user-1", displayName: "Tester" }

beforeEach(() => {
  idbPersistences.length = 0
  capturedYdoc = null
})

afterEach(() => {
  vi.clearAllMocks()
})

// Reproduces the race that caused content to disappear in the React document
// editor (issue #7495 / DECIDE-8Q2). useCollaboration captures plugins at
// session creation time when yXmlFragment is empty. If the fragment populates
// (via IndexedDB load or network sync) between session creation and
// EditorView mount, the editor must still reflect that content. This is the
// `_forceRerender` path in y-prosemirror's ySyncPlugin, which runs only when
// no `mapping` option is passed.
describe("useCollaboration handles late-populating yXmlFragment", () => {
  test("EditorView built from session plugins reflects yXmlFragment content that arrived after session creation", async () => {
    const { result, unmount } = renderHook(() =>
      useCollaboration({
        channelsClient: fakeChannelsClient,
        stream: "document",
        params: { document_id: "doc-1" },
        currentUser,
        initialContent: null,
      })
    )

    await waitFor(() => {
      expect(capturedYdoc).not.toBeNull()
      expect(result.current.plugins.length).toBeGreaterThan(0)
    })

    // Simulate IndexedDB or network sync populating the doc after the session
    // was created but before the EditorView is constructed.
    const yXmlFragment = capturedYdoc!.getXmlFragment("prosemirror")
    expect(yXmlFragment.length).toBe(0)
    prosemirrorToYXmlFragment(parse("Hello world"), yXmlFragment)
    expect(yXmlFragment.length).toBeGreaterThan(0)

    const state = EditorState.create({ schema, plugins: result.current.plugins })
    const mount = document.createElement("div")
    const view = new EditorView(mount, { state })
    try {
      // Fails before fix: ySyncPlugin received a pre-built (empty) mapping at
      // session creation, which suppresses `_forceRerender` in its `view(view)`
      // callback. The populating updates that arrived after observeDeep was
      // registered but before this point are not projected to the editor.
      // Passes after fix: no mapping option is passed, so `_forceRerender`
      // runs once during view construction and reflects the current fragment.
      expect(view.state.doc.textContent).toBe("Hello world")
    } finally {
      view.destroy()
      unmount()
    }
  })
})
