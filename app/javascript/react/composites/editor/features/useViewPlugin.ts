import { Plugin } from "prosemirror-state"
import { useCallback, useEffect, useMemo, useRef } from "react"

import { serialize, withoutTrailingEmptyBlocks } from "~/richText/schema"
import type { EditorFeature } from "../types"

interface UseViewPluginOptions {
  onChange: (markdown: string) => void
  debounceMs?: number
}

interface UseViewPluginResult extends EditorFeature {
  // Drops any pending debounced serialize without invoking onChange. Call
  // synchronously before an action whose follow-up state change would be
  // clobbered by a late flush (e.g. chat composer pre-send).
  cancel: () => void
}

// The chat composer uses DEBOUNCE_MS to coalesce rapid keystrokes into one
// serialize. The full markdown pipeline (PM → mdast → normalize → stringify)
// is O(doc-size) and dominates per-keystroke INP on long drafts; consumers
// tolerate this delay because send-time freshness comes from `useEnterToSend`
// re-serializing `view.state.doc` directly.
export const DEBOUNCE_MS = 150

// View plugin that fires onChange only when document content changes.
// Using a view plugin avoids the infinite loop that useEditorEffect would
// cause (it fires on every state update, including the one triggered by
// onChange -> setDraft -> re-render).
export function useViewPlugin({ onChange, debounceMs }: UseViewPluginOptions): UseViewPluginResult {
  const onChangeRef = useRef(onChange)
  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  // Bridges the per-view debounce timer to the imperative cancel().
  const cancelRef = useRef<() => void>(() => {})

  const plugin = useMemo(
    () => {
      // Captured once — mirrors `onChangeRef` to keep the plugin referentially
      // stable. Runtime changes aren't supported (no consumer needs them).
      const delay = debounceMs ?? 0
      return new Plugin({
        view(editorView) {
          let debounceTimer: ReturnType<typeof setTimeout> | null = null
          cancelRef.current = () => {
            if (debounceTimer === null) return
            clearTimeout(debounceTimer)
            debounceTimer = null
          }
          return {
            update(view, prevState) {
              if (view.state.doc.eq(prevState.doc)) return

              // Capture `view` (not `view.state.doc`) so the timer reads the
              // latest doc when the burst settles, not the doc at schedule time.
              if (delay > 0) {
                if (debounceTimer !== null) clearTimeout(debounceTimer)
                debounceTimer = setTimeout(() => {
                  debounceTimer = null
                  onChangeRef.current(serialize(withoutTrailingEmptyBlocks(view.state.doc)))
                }, delay)
              } else {
                onChangeRef.current(serialize(withoutTrailingEmptyBlocks(view.state.doc)))
              }
              // Defer scrollIntoView to a microtask so the dispatch
              // doesn't trigger flushSync while React is mid-render
              // (e.g. when the emoji suggester opens on ':').
              queueMicrotask(() => {
                if (!view.isDestroyed) {
                  view.dispatch(view.state.tr.scrollIntoView())
                }
              })
            },
            destroy() {
              if (debounceTimer === null) return
              clearTimeout(debounceTimer)
              debounceTimer = null
              // Flush so panel-close / route-change unmounts persist the
              // last ≤debounceMs of typing. Consumers that need to suppress
              // this on an action-triggered remount call cancel() first.
              onChangeRef.current(serialize(withoutTrailingEmptyBlocks(editorView.state.doc)))
            },
          }
        },
      })
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  )

  const cancel = useCallback(() => cancelRef.current(), [])

  return useMemo(() => ({ plugins: [plugin], cancel }), [plugin, cancel])
}
