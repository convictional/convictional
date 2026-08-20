import { computePosition, flip, offset, shift } from "@floating-ui/dom"
import Fuse from "fuse.js"
import { ChangeReason, RangeWithCursor, SuggestChangeHandlerProps } from "prosemirror-suggest"
import { EditorView } from "prosemirror-view"
import { useCallback, useEffect, useRef, useState } from "react"

export interface SuggesterState<T> {
  shouldShow: boolean
  results: T[]
  highlightedIndex: number
}

export interface SuggesterActions<T> {
  select: (item: T) => void
  dismiss: () => void
  setHighlightedIndex: (index: number) => void
}

interface UseSuggesterOptions<T> {
  // The name must match the suggester name in the prosemirror-suggest config,
  // used to find the decoration element (`.suggest-{name}`) for positioning.
  name: string
  items: T[] | (() => Promise<T[]>)
  fuseKeys: string[]
  maxResults?: number
  onSelect: (item: T, range: RangeWithCursor, view: EditorView) => void
  // When the component reorders results for display (e.g. collaborators first),
  // provide a sort function so keyboard nav indexes match rendered order.
  sortResults?: (results: T[]) => T[]
  viewRef: React.RefObject<EditorView | null>
}

// Registered by the component, called by the suggest plugin created in DocumentEditor.
// This indirection is needed because the plugin must exist before ProseMirror mounts,
// but the component's state setters don't exist until after mount.
export type SuggesterCallback = (props: SuggestChangeHandlerProps) => void

export function useSuggester<T>({
  name,
  items,
  fuseKeys,
  maxResults = 20,
  onSelect,
  sortResults,
  viewRef,
}: UseSuggesterOptions<T>) {
  const [state, setState] = useState<SuggesterState<T>>({
    shouldShow: false,
    results: [],
    highlightedIndex: 0,
  })

  const dropdownRef = useRef<HTMLDivElement>(null)
  // Function items (e.g. emoji) are fetched once and cached for the editor
  // lifetime. Array items (e.g. store-backed mentions) are read live, so a list
  // that populates after the editor mounts — or changes mid-session — is picked
  // up on the next `@`.
  const itemsCache = useRef<T[] | null>(null)
  const fuseRef = useRef<Fuse<T> | null>(null)
  // Always holds the latest range from prosemirror-suggest, so selectItem
  // doesn't capture a stale value from the render closure.
  const rangeRef = useRef<RangeWithCursor>({ from: 0, to: 0, cursor: 0 })

  const resolveItems = useCallback(async (): Promise<T[]> => {
    if (Array.isArray(items)) {
      fuseRef.current = new Fuse(items, { keys: fuseKeys, threshold: 0.3 })
      return items
    }
    if (itemsCache.current) return itemsCache.current
    const resolved = await items()
    itemsCache.current = resolved
    fuseRef.current = new Fuse(resolved, { keys: fuseKeys, threshold: 0.3 })
    return resolved
  }, [items, fuseKeys])

  const search = useCallback(
    async (query: string): Promise<T[]> => {
      const allItems = await resolveItems()
      if (!query) return allItems.slice(0, maxResults)
      return fuseRef
        .current!.search(query)
        .map(r => r.item)
        .slice(0, maxResults)
    },
    [resolveItems, maxResults]
  )

  const positionDropdown = useCallback((referenceEl: Element) => {
    const dropdown = dropdownRef.current
    if (!dropdown) return

    computePosition(referenceEl, dropdown, {
      placement: "bottom-start",
      middleware: [offset(4), flip(), shift({ padding: 8 })],
    }).then(({ x, y }) => {
      dropdown.style.left = `${x}px`
      dropdown.style.top = `${y}px`
    })
  }, [])

  // prosemirror-suggest adds a span with class `suggest suggest-{name}` around
  // the matched text. We use that as the Floating UI reference element.
  const findDecorationEl = useCallback(() => document.querySelector(`.suggest-${name}`), [name])

  // prosemirror-suggest does not clear its internal _handlerMatches after
  // firing onChange. When @handlewithcare/react-prosemirror triggers a
  // view.update during the React re-render (caused by our setState), the
  // plugin's changeHandler finds the same pending match and fires onChange
  // again — creating an infinite setState → re-render → onChange loop.
  // Deduplicate by tracking the last range we processed.
  const lastChangeRef = useRef<{ from: number; to: number } | null>(null)

  const onChange: SuggesterCallback = useCallback(
    ({ changeReason, exitReason, query, range }) => {
      if (exitReason) {
        // Same re-entrancy as the non-exit branch: view.update re-fires onChange
        // with the same exitReason. If we already processed the exit (ref is null),
        // skip the setState to break the loop.
        if (lastChangeRef.current === null) return
        lastChangeRef.current = null
        setState(prev => ({ ...prev, shouldShow: false }))
        return
      }

      const last = lastChangeRef.current
      if (last && last.from === range.from && last.to === range.to) return
      lastChangeRef.current = { from: range.from, to: range.to }

      rangeRef.current = range
      const resetIndex = changeReason === ChangeReason.Start

      search(query.full).then(rawResults => {
        const results = sortResults ? sortResults(rawResults) : rawResults
        setState(prev => ({
          shouldShow: true,
          results,
          highlightedIndex: resetIndex ? 0 : Math.min(prev.highlightedIndex, results.length - 1),
        }))

        requestAnimationFrame(() => {
          const el = findDecorationEl()
          if (el) positionDropdown(el)
        })
      })
    },
    [search, sortResults, positionDropdown, findDecorationEl]
  )

  const selectItem = useCallback(
    (item: T) => {
      const view = viewRef.current
      if (!view) return
      lastChangeRef.current = null
      onSelect(item, rangeRef.current, view)
      setState(prev => ({ ...prev, shouldShow: false }))
    },
    [onSelect, viewRef]
  )

  const dismiss = useCallback(() => {
    lastChangeRef.current = null
    setState(prev => ({ ...prev, shouldShow: false }))
  }, [])

  const setHighlightedIndex = useCallback((index: number) => {
    setState(prev => ({ ...prev, highlightedIndex: index }))
  }, [])

  const navItems = state.results

  useEffect(() => {
    if (!state.shouldShow) return

    const handleKeyDown = (e: KeyboardEvent) => {
      const len = navItems.length
      if (!len) return

      if (e.key === "ArrowDown") {
        e.preventDefault()
        e.stopPropagation()
        setState(prev => {
          const next = (prev.highlightedIndex + 1) % len
          scrollToItem(next)
          return { ...prev, highlightedIndex: next }
        })
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        e.stopPropagation()
        setState(prev => {
          const next = (prev.highlightedIndex - 1 + len) % len
          scrollToItem(next)
          return { ...prev, highlightedIndex: next }
        })
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault()
        e.stopPropagation()
        const item = navItems[state.highlightedIndex]
        if (item) selectItem(item)
      } else if (e.key === "Escape") {
        e.preventDefault()
        e.stopPropagation()
        dismiss()
      }
    }

    window.addEventListener("keydown", handleKeyDown, true)
    return () => window.removeEventListener("keydown", handleKeyDown, true)
  }, [state.shouldShow, state.highlightedIndex, navItems, selectItem, dismiss])

  // Reposition on dropdown resize
  useEffect(() => {
    if (!state.shouldShow || !dropdownRef.current) return

    const observer = new ResizeObserver(() => {
      const el = findDecorationEl()
      if (el) positionDropdown(el)
    })

    observer.observe(dropdownRef.current)
    return () => observer.disconnect()
  }, [state.shouldShow, positionDropdown, findDecorationEl])

  return {
    state,
    dropdownRef,
    onChange,
    actions: { select: selectItem, dismiss, setHighlightedIndex },
  }
}

function scrollToItem(index: number) {
  requestAnimationFrame(() => {
    const items = document.querySelectorAll("[data-suggester-item]")
    items[index]?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  })
}
