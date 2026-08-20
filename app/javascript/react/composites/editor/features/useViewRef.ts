import { Plugin } from "prosemirror-state"
import { EditorView } from "prosemirror-view"
import { useMemo, useRef } from "react"

export function useViewRef(): { viewRef: React.RefObject<EditorView | null>; plugin: Plugin } {
  const viewRef = useRef<EditorView | null>(null)

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
      }),
    []
  )
  /* eslint-enable react-hooks/refs */

  return { viewRef, plugin }
}
