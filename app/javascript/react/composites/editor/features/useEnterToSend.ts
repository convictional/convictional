import { Plugin } from "prosemirror-state"
import { EditorView } from "prosemirror-view"
import { useCallback, useEffect, useMemo, useRef } from "react"

import { isBlankMarkdown, serialize, withoutTrailingEmptyBlocks } from "~/richText/schema"
import { getEnterCommand } from "~/richText/schema/keymap"
import type { EditorFeature } from "../types"

const blockAwareEnter = getEnterCommand()

interface UseEnterToSendOptions {
  onSend: (markdown: string) => void
  // When false, Enter is not bound to send and falls through to the editor's
  // default newline behavior. The send() method still works for explicit
  // submits (e.g. a tap on a Send button on mobile).
  interceptEnter?: boolean
  // When true, only Cmd/Ctrl+Enter submits and plain Enter inserts a newline.
  // Post comments use this to restore their pre-React-migration behavior; chat
  // leaves it false, where plain Enter submits (but defers to block handling
  // inside code blocks and lists). Shift+Enter starts a new block regardless.
  requireModifier?: boolean
}

export interface EnterToSendFeature extends EditorFeature {
  send: () => void
}

function sendFromView(view: EditorView, onSend: (markdown: string) => void) {
  const markdown = serialize(withoutTrailingEmptyBlocks(view.state.doc))
  if (isBlankMarkdown(markdown)) return
  onSend(markdown.trimEnd())
  // Don't clear the editor here — the caller clears it on success by rotating
  // claimId (key={claimId} in ComposeBar), which remounts a fresh editor.
  // Clearing eagerly means a network failure leaves the user with no way to
  // retry without retyping their message.
  view.focus()
}

export function useEnterToSend({
  onSend,
  interceptEnter = true,
  requireModifier = false,
}: UseEnterToSendOptions): EnterToSendFeature {
  const onSendRef = useRef(onSend)
  useEffect(() => {
    onSendRef.current = onSend
  }, [onSend])

  const interceptEnterRef = useRef(interceptEnter)
  useEffect(() => {
    interceptEnterRef.current = interceptEnter
  }, [interceptEnter])

  const requireModifierRef = useRef(requireModifier)
  useEffect(() => {
    requireModifierRef.current = requireModifier
  }, [requireModifier])

  const viewRef = useRef<EditorView | null>(null)

  // Refs are accessed only inside ProseMirror callbacks (handleKeyDown, view
  // lifecycle), never during React render.
  /* eslint-disable react-hooks/refs */
  const plugin = useMemo(
    () =>
      new Plugin({
        view(view) {
          viewRef.current = view
          return {
            update(view) {
              viewRef.current = view
            },
            destroy() {
              viewRef.current = null
            },
          }
        },
        props: {
          handleKeyDown(view: EditorView, event: KeyboardEvent) {
            if (!interceptEnterRef.current) return false
            if (event.key !== "Enter") return false

            const hasModifier = event.metaKey || event.ctrlKey
            if (hasModifier) {
              // A hotkey submit is terminal: stop the keystroke from bubbling to
              // ancestor keydown listeners (e.g. a post draft's ⌘↵-to-publish
              // shortcut) so submitting a comment never also acts on the
              // surrounding resource.
              event.preventDefault()
              event.stopPropagation()
              sendFromView(view, onSendRef.current)
              return true
            }

            // Shift+Enter starts a new block, never sends. Decline it here and
            // let the shared keymap's Shift-Enter binding perform the split, so
            // every composer (chat, post body, post comments) shares one behavior.
            if (event.shiftKey) return false

            if (requireModifierRef.current) return false

            // Probe (no dispatch): if a block command — newline in code, split
            // list item — would handle this Enter, defer to the editor keymap
            // instead of submitting.
            if (blockAwareEnter(view.state)) return false

            // Terminal submit — stop propagation as in the ⌘↵ branch above.
            event.preventDefault()
            event.stopPropagation()
            sendFromView(view, onSendRef.current)
            return true
          },
        },
      }),
    []
  )

  const send = useCallback(() => {
    if (viewRef.current) {
      sendFromView(viewRef.current, onSendRef.current)
    }
  }, [])
  /* eslint-enable react-hooks/refs */

  return { plugins: [plugin], send }
}
