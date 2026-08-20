import { EditorView } from "prosemirror-view"

import { serialize, withoutTrailingEmptyBlocks } from "~/richText/schema"

// Read the editor's live document at send time rather than a value cached from
// the last onChange. A draft whose body arrives via Yjs collaboration (loaded
// from IndexedDB or synced over the WebSocket) is injected into the view at
// construction by y-prosemirror's `_forceRerender` — no edit transaction fires,
// so a `useViewPlugin` onChange listener never observes it. Sending the cached
// value would then POST an empty `message_body`, silently dropping body text the
// user can plainly see (seen when users reply-and-send on mobile without touching
// the body). This mirrors the chat composer's send-time re-serialize in
// `useEnterToSend`. The fallback only covers the rare window where the view ref
// isn't attached yet.
export function serializeEditorBody(view: EditorView | null, fallback: string): string {
  return view ? serialize(withoutTrailingEmptyBlocks(view.state.doc)) : fallback
}
