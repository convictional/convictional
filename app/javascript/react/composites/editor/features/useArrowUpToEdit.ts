import { Plugin } from "prosemirror-state"
import { EditorView } from "prosemirror-view"
import { useEffect, useMemo, useRef } from "react"

import { isBlankMarkdown, serialize } from "~/richText/schema"
import type { EditorFeature } from "../types"

interface UseArrowUpToEditOptions {
  onEditPrevious: () => boolean
}

// Slack-style: pressing Up in an empty composer edits the user's last message.
// We only trigger when the doc is empty so an in-progress draft is never lost
// to a stray ArrowUp.
export function useArrowUpToEdit({ onEditPrevious }: UseArrowUpToEditOptions): EditorFeature {
  const onEditPreviousRef = useRef(onEditPrevious)
  useEffect(() => {
    onEditPreviousRef.current = onEditPrevious
  }, [onEditPrevious])

  /* eslint-disable react-hooks/refs */
  const plugin = useMemo(
    () =>
      new Plugin({
        props: {
          handleKeyDown(view: EditorView, event: KeyboardEvent) {
            if (event.key !== "ArrowUp") return false
            if (event.shiftKey || event.altKey || event.metaKey || event.ctrlKey) return false
            if (!isBlankMarkdown(serialize(view.state.doc))) return false
            if (!onEditPreviousRef.current()) return false
            event.preventDefault()
            return true
          },
        },
      }),
    []
  )
  /* eslint-enable react-hooks/refs */

  return { plugins: [plugin] }
}
