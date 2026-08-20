import { nameToEmoji } from "gemoji"
import { getSuggestPluginState, RangeWithCursor, Suggester } from "prosemirror-suggest"
import { EditorView } from "prosemirror-view"
import { useCallback, useEffect, useMemo, useRef, type RefObject } from "react"

import { schema } from "~/richText/schema"
import type { EditorFeature } from "../types"
import { SuggesterActions, SuggesterCallback, SuggesterState, useSuggester } from "./useSuggester"
import { useViewRef } from "./useViewRef"

interface Emoji {
  name: string
  emoji: string
}

const allEmojis: Emoji[] = Object.entries(nameToEmoji).map(([name, emoji]) => ({ name, emoji }))

const invalidNodes = [schema.nodes.heading.name, schema.nodes.code_block.name]
const invalidMarks = [schema.marks.code.name]

export interface EmojiState {
  suggesterState: SuggesterState<Emoji>
  dropdownRef: RefObject<HTMLDivElement | null>
  actions: SuggesterActions<Emoji>
}

export interface EmojiFeature extends EditorFeature {
  state: EmojiState
}

export function useEmojis(): EmojiFeature {
  const { viewRef, plugin: viewPlugin } = useViewRef()
  const onChangeRef = useRef<SuggesterCallback | null>(null)

  const suggester: Suggester = useMemo(
    () => ({
      char: ":",
      name: "emojis",
      matchOffset: 1,
      invalidNodes,
      invalidMarks,
      // onChange must fire from appendTransaction so the dropdown works when the
      // editor is nested inside another ProseMirror editor.
      appendTransaction: true,
      onChange: props => onChangeRef.current?.(props),
    }),
    []
  )

  const insertEmoji = useCallback((item: Emoji, range: RangeWithCursor, view: EditorView) => {
    const { from, to } = range
    const tr = view.state.tr.replaceWith(from, to, schema.text(item.emoji + " "))
    getSuggestPluginState(view.state).ignoreNextExit()
    view.dispatch(tr)
  }, [])

  const {
    state: suggesterState,
    dropdownRef,
    onChange,
    actions,
  } = useSuggester<Emoji>({
    name: "emojis",
    items: allEmojis,
    fuseKeys: ["name"],
    maxResults: 20, // gemoji has ~1800 entries; cap results to keep the dropdown scannable
    onSelect: insertEmoji,
    viewRef,
  })

  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  // Space confirms the highlighted emoji, matching user expectation that space accepts a suggestion
  useEffect(() => {
    if (!suggesterState.shouldShow) return

    const handleSpace = (e: KeyboardEvent) => {
      if (e.key !== " ") return
      const item = suggesterState.results[suggesterState.highlightedIndex]
      if (item) {
        e.preventDefault()
        e.stopPropagation()
        actions.select(item)
      }
    }

    window.addEventListener("keydown", handleSpace, true)
    return () => window.removeEventListener("keydown", handleSpace, true)
  }, [suggesterState.shouldShow, suggesterState.results, suggesterState.highlightedIndex, actions])

  return {
    plugins: [viewPlugin],
    suggesters: [suggester],
    state: { suggesterState, dropdownRef, actions },
  }
}
