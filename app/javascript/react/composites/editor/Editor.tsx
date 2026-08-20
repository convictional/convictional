import { ProseMirror, reactKeys } from "@handlewithcare/react-prosemirror"
import { dropCursor } from "prosemirror-dropcursor"
import { gapCursor } from "prosemirror-gapcursor"
import { history } from "prosemirror-history"
import type { Node } from "prosemirror-model"
import { EditorState, Plugin } from "prosemirror-state"
import { suggest } from "prosemirror-suggest"
import { useState, type ReactNode } from "react"

import { clickToEnd } from "~/richText/plugins/clickToEnd"
import { clipboardPlugin } from "~/richText/plugins/clipboard"
import placeholder from "~/richText/plugins/placeholder"
import { schema, plugins as schemaPlugins, nodeViews as schemaNodeViews } from "~/richText/schema"
import { getInputRules } from "~/richText/schema/inputRules"
import { getKeymap } from "~/richText/schema/keymap"

import { QuotedHtmlNodeView } from "./QuotedHtmlNodeView"
import { installSafeSelectionCollapse } from "./safeSelectionCollapse"
import type { EditorFeature } from "./types"

// The shared `quoted_html` toDOM returns a DOM node; @handlewithcare/react-prosemirror
// rejects anything other than strings/arrays. Supplying a NodeView here bypasses
// toDOM without touching the shared schema definition.
// (v3 renamed this prop from `customNodeViews` to `nodeViews` — native node view
// constructors, as ProseMirror defines them.)
const nodeViews = {
  ...schemaNodeViews,
  quoted_html: (node: Node) => new QuotedHtmlNodeView(node),
}

installSafeSelectionCollapse()

export { ProseMirrorDoc as EditorContent } from "@handlewithcare/react-prosemirror"

interface EditorProps {
  features: EditorFeature[]
  doc?: Node
  placeholder?: string
  className?: string
  autoFocus?: boolean
  // Off when a surrounding box dropzone already shows a "Drop to upload"
  // overlay, so the native drop-cursor line doesn't clash with it.
  showDropCursor?: boolean
  children?: ReactNode
}

export function Editor({
  features,
  doc,
  placeholder: placeholderText,
  className,
  autoFocus,
  showDropCursor = true,
  children,
}: EditorProps) {
  // Computed once on mount — ProseMirror is uncontrolled after initialization.
  // Consumers gate rendering (e.g. collaboration.ready) so features are stable at mount time.
  const [defaultState] = useState(() => {
    const plugins: Plugin[] = [
      reactKeys(),
      clipboardPlugin,
      clickToEnd,
      // Feature plugins are ordered before getKeymap() so features like
      // enter-to-send can intercept keys (e.g. Mod+Enter) before the
      // shared keymap's no-op handlers swallow them.
      ...features.flatMap(f => f.plugins),
      getKeymap(),
      getInputRules(),
      ...schemaPlugins,
      ...(showDropCursor ? [dropCursor()] : []),
      gapCursor(),
    ]

    // The shared keymap binds Mod-z/Mod-Shift-z to prosemirror-history. Register
    // it unless a feature (collaboration's yUndoPlugin) already provides undo/redo;
    // the two history systems must not coexist. Order doesn't matter — history is
    // a state plugin, not a key handler.
    if (!features.some(f => f.providesHistory)) plugins.push(history())

    if (placeholderText) plugins.push(placeholder(placeholderText))
    plugins.push(
      new Plugin({
        props: {
          attributes: { class: ["markdown-content", className].filter(Boolean).join(" "), spellcheck: "true" },
        },
      })
    )
    if (autoFocus) {
      plugins.push(
        new Plugin({
          view(view) {
            view.focus()
            return {}
          },
        })
      )
    }

    // Suggesters must come after Yjs plugins — prosemirror-suggest uses
    // appendTransaction which returns new transactions. If it runs before
    // ySyncPlugin, the sync plugin tries to serialize suggest's internal
    // state objects, causing a stack overflow in Yjs's writeAny.
    const allSuggesters = features.flatMap(f => f.suggesters ?? [])
    if (allSuggesters.length > 0) {
      plugins.push(suggest(...allSuggesters))
    }

    return EditorState.create({ schema, doc, plugins })
  })

  return (
    <ProseMirror defaultState={defaultState} nodeViews={nodeViews}>
      {children}
    </ProseMirror>
  )
}
