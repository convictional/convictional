import type { Plugin } from "prosemirror-state"
import type { Suggester } from "prosemirror-suggest"

export type SyncStatus = "connecting" | "connected" | "disconnected"

export interface EditorFeature {
  plugins: Plugin[]
  suggesters?: Suggester[]
  // Set when a feature supplies its own undo/redo (e.g. collaboration's
  // yUndoPlugin). The Editor then skips prosemirror-history, which must not
  // coexist with yUndoPlugin.
  providesHistory?: boolean
}
