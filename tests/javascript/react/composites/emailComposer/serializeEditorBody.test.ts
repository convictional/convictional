import { EditorView } from "prosemirror-view"
import { describe, expect, it } from "vitest"

import { serializeEditorBody } from "~/react/composites/emailComposer/serializeEditorBody"
import { parse } from "~/richText/schema"

// A view whose doc was populated by collaboration sync, not by a keystroke —
// the onChange-fed fallback ref is still empty here.
function viewWithBody(markdown: string): EditorView {
  return { state: { doc: parse(markdown) } } as unknown as EditorView
}

describe("serializeEditorBody", () => {
  it("serializes the live document, ignoring a stale empty fallback", () => {
    // The regression: a draft loaded from Yjs (IndexedDB / WebSocket) shows body
    // text the user never typed, so the onChange ref is "". Sending the ref POSTs
    // an empty body, silently dropping the content the user can see.
    expect(serializeEditorBody(viewWithBody("Hello there"), "")).toBe("Hello there\n")
  })

  it("prefers the live document even when it diverges from the fallback ref", () => {
    expect(serializeEditorBody(viewWithBody("Latest body"), "stale body")).toBe("Latest body\n")
  })

  it("falls back to the ref only when no view is attached", () => {
    expect(serializeEditorBody(null, "fallback body")).toBe("fallback body")
  })

  it("drops the trailing empty paragraph an upload leaves behind (no stray blank line)", () => {
    // The attachments plugin lands the caret in a fresh empty paragraph after an upload batch. If
    // the user sends without typing into it, that paragraph must not become a "<br />" in the sent
    // body — the same trailing-empty-block stripping chat's send path applies.
    expect(serializeEditorBody(viewWithBody("![](/a)\n\n<br />"), "")).toBe("![](/a)\n")
  })
})
