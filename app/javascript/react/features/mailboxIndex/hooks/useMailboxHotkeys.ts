import { useCallback, useEffect, useRef, useState } from "react"

import type { MailboxEntry } from "../types"

const KEYBOARD_ACTIVE_TIMEOUT_MS = 2000

interface UseMailboxHotkeysArgs {
  entries: MailboxEntry[]
}

export interface MailboxHotkeysApi {
  selectedIndex: number
  selectedId: string | null
  isKeyboardActive: boolean
  selectIndex: (index: number) => void
  selectNext: () => void
  selectPrevious: () => void
  // Returns the selected entry (if any) for the consumer to act on.
  selectedEntry: () => MailboxEntry | null
  notifyKeyboardActivity: () => void
}

export function useMailboxHotkeys({ entries }: UseMailboxHotkeysArgs): MailboxHotkeysApi {
  const [rawSelectedIndex, setSelectedIndex] = useState(0)
  const [isKeyboardActive, setIsKeyboardActive] = useState(false)
  const keyboardTimeoutRef = useRef<number | null>(null)
  const isProgrammaticScrollRef = useRef(false)
  const entriesRef = useRef(entries)
  useEffect(() => {
    entriesRef.current = entries
  })

  // Clamp selection on read so the entries list shrinking (e.g., after archive)
  // doesn't require a state-syncing effect.
  const selectedIndex = entries.length === 0 ? 0 : Math.min(Math.max(rawSelectedIndex, 0), entries.length - 1)

  const exitKeyboardActiveState = useCallback(() => {
    setIsKeyboardActive(false)
    if (keyboardTimeoutRef.current !== null) {
      clearTimeout(keyboardTimeoutRef.current)
      keyboardTimeoutRef.current = null
    }
  }, [])

  const enterKeyboardActiveState = useCallback(() => {
    setIsKeyboardActive(true)
    if (keyboardTimeoutRef.current !== null) {
      clearTimeout(keyboardTimeoutRef.current)
    }
    keyboardTimeoutRef.current = window.setTimeout(() => {
      exitKeyboardActiveState()
    }, KEYBOARD_ACTIVE_TIMEOUT_MS)
  }, [exitKeyboardActiveState])

  // Exit keyboard-active mode when the user manually scrolls (mirrors
  // emailThreads/hotkeys.ts:106-117). Programmatic scrolls from selectIndex are
  // ignored via the ref flag below.
  useEffect(() => {
    const onUserScroll = () => {
      if (isProgrammaticScrollRef.current) return
      setIsKeyboardActive(prev => {
        if (!prev) return prev
        if (keyboardTimeoutRef.current !== null) {
          clearTimeout(keyboardTimeoutRef.current)
          keyboardTimeoutRef.current = null
        }
        return false
      })
    }
    window.addEventListener("wheel", onUserScroll, { passive: true })
    window.addEventListener("touchstart", onUserScroll, { passive: true })
    return () => {
      window.removeEventListener("wheel", onUserScroll)
      window.removeEventListener("touchstart", onUserScroll)
    }
  }, [])

  const scrollSelectedIntoView = useCallback((index: number) => {
    const id = entriesRef.current[index]?.id
    if (!id) return
    const el = document.getElementById(`mailbox-entry-${id}`)
    if (!el) return
    isProgrammaticScrollRef.current = true
    el.scrollIntoView({ block: "nearest" })
    setTimeout(() => {
      isProgrammaticScrollRef.current = false
    }, 100)
  }, [])

  const selectIndex = useCallback(
    (index: number) => {
      enterKeyboardActiveState()
      setSelectedIndex(index)
      scrollSelectedIntoView(index)
    },
    [enterKeyboardActiveState, scrollSelectedIntoView]
  )

  const selectNext = useCallback(() => {
    const list = entriesRef.current
    if (list.length === 0) return
    const next = Math.min(selectedIndex + 1, list.length - 1)
    selectIndex(next)
    if (selectedIndex + 1 >= list.length) {
      isProgrammaticScrollRef.current = true
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" })
      setTimeout(() => {
        isProgrammaticScrollRef.current = false
      }, 500)
    }
  }, [selectedIndex, selectIndex])

  const selectPrevious = useCallback(() => {
    if (selectedIndex <= 0) {
      isProgrammaticScrollRef.current = true
      window.scrollTo({ top: 0, behavior: "smooth" })
      setTimeout(() => {
        isProgrammaticScrollRef.current = false
      }, 500)
      return
    }
    selectIndex(selectedIndex - 1)
  }, [selectedIndex, selectIndex])

  const selectedEntry = useCallback((): MailboxEntry | null => {
    return entriesRef.current[selectedIndex] ?? null
  }, [selectedIndex])

  const notifyKeyboardActivity = useCallback(() => {
    enterKeyboardActiveState()
  }, [enterKeyboardActiveState])

  const selectedId = entries[selectedIndex]?.id ?? null

  return {
    selectedIndex,
    selectedId,
    isKeyboardActive,
    selectIndex,
    selectNext,
    selectPrevious,
    selectedEntry,
    notifyKeyboardActivity,
  }
}
