import { type KeyboardEvent, useCallback, useEffect, useMemo, useRef } from "react"

import { boostedNavigate } from "~/react/shared/boostedNavigate"
import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { QuickLinkForm } from "./active/QuickLinkForm"
import { ResearchForm } from "./active/ResearchForm"
import { fetchCommands, fetchLookup, fetchPeople, fetchRecent, type PeopleResponse, trackSearch } from "./api"
import { CommandsMode, filterCommands } from "./modes/CommandsMode"
import { RecentMode } from "./modes/RecentMode"
import { SearchMode } from "./modes/SearchMode"
import { PaletteInput } from "./PaletteInput"
import { PaletteModal } from "./PaletteModal"
import { usePaletteStore } from "./store"
import type { Command, LookupResult } from "./types"
import { useArrowKeySelection } from "./useArrowKeySelection"
import { useDebouncedSearch } from "./useDebouncedSearch"
import { useGlobalHotkey } from "./useGlobalHotkey"

const MIN_QUERY_LENGTH = 2

function placeholderFor(mode: string, filtered: boolean): string {
  if (filtered) return "Search"
  if (mode === "active") return ""
  return "Search or type '/' for commands"
}

export function CommandPalette() {
  // Field-scoped subscriptions so a `setSelectedIndex` doesn't re-render the
  // whole palette. Actions returned by zustand are stable refs across renders,
  // so we can safely include them in effect/callback deps.
  const isOpen = usePaletteStore(s => s.isOpen)
  const mode = usePaletteStore(s => s.mode)
  const input = usePaletteStore(s => s.input)
  const filterGlobalId = usePaletteStore(s => s.filterGlobalId)
  const activeCommandKey = usePaletteStore(s => s.activeCommandKey)
  const query = usePaletteStore(s => s.query)
  const results = usePaletteStore(s => s.results)
  const filter = usePaletteStore(s => s.filter)
  const recent = usePaletteStore(s => s.recent)
  const commands = usePaletteStore(s => s.commands)
  const selectedIndex = usePaletteStore(s => s.selectedIndex)
  const mouseEnabled = usePaletteStore(s => s.mouseEnabled)
  const initialMouse = usePaletteStore(s => s.initialMouse)
  const isLoading = usePaletteStore(s => s.isLoading)
  const showTimeoutError = usePaletteStore(s => s.showTimeoutError)

  const toggle = usePaletteStore(s => s.toggle)
  const close = usePaletteStore(s => s.close)
  const setInput = usePaletteStore(s => s.setInput)
  const setMode = usePaletteStore(s => s.setMode)
  const setResults = usePaletteStore(s => s.setResults)
  const setRecent = usePaletteStore(s => s.setRecent)
  const setCommands = usePaletteStore(s => s.setCommands)
  const setLoading = usePaletteStore(s => s.setLoading)
  const setTimeoutError = usePaletteStore(s => s.setTimeoutError)
  const setSelectedIndex = usePaletteStore(s => s.setSelectedIndex)
  const setMouseEnabled = usePaletteStore(s => s.setMouseEnabled)
  const setInitialMouse = usePaletteStore(s => s.setInitialMouse)
  const setFilter = usePaletteStore(s => s.setFilter)
  const clearFilter = usePaletteStore(s => s.clearFilter)
  const activateCommand = usePaletteStore(s => s.activateCommand)
  const exitCommand = usePaletteStore(s => s.exitCommand)
  const goToRecent = usePaletteStore(s => s.goToRecent)
  const capturePendingTracking = usePaletteStore(s => s.capturePendingTracking)
  const consumePendingTracking = usePaletteStore(s => s.consumePendingTracking)

  const inputRef = useRef<HTMLInputElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  useGlobalHotkey(toggle)

  // Boost the result/recent/see-all anchors so opening one stays a same-realm
  // navigation instead of a hard reload that strands the realm (#8744). htmx only
  // wires boost handlers for anchors present at scan time, so re-process when the
  // modal opens or the anchor-bearing modes/lists change.
  useBoostIslandLinks(rootRef, [isOpen, mode, results, recent, query])

  // Cross-island toggle from SearchButton click.
  useEffect(() => {
    const handler = () => toggle()
    window.addEventListener("command-palette:toggle", handler)
    return () => window.removeEventListener("command-palette:toggle", handler)
  }, [toggle])

  // Load recent on open / mode change. With a filter active and no query, the
  // people endpoint returns "recent activity by that author" — same shape as
  // lookup, but constrained.
  useEffect(() => {
    if (!isOpen) return
    const controller = new AbortController()
    if (filterGlobalId) {
      // Reading input via getState() so this effect doesn't re-fire on every
      // keystroke; the debounce branch handles >= MIN_QUERY_LENGTH input.
      if (usePaletteStore.getState().input.length >= MIN_QUERY_LENGTH) return
      fetchPeople(filterGlobalId, "", controller.signal)
        .then(res => {
          if (controller.signal.aborted) return
          setResults(res.results, "", res.filter)
        })
        .catch(() => {})
    } else if (mode === "recent") {
      fetchRecent(controller.signal)
        .then(res => {
          if (controller.signal.aborted) return
          setRecent(res.recent_items)
        })
        .catch(() => {})
    }
    return () => controller.abort()
  }, [isOpen, mode, filterGlobalId, setResults, setRecent])

  // Lazy-load commands on first commands-mode entry (and refetch after quick-link saves).
  useEffect(() => {
    if (!isOpen) return
    if (mode !== "commands") return
    if (commands !== null) return
    const controller = new AbortController()
    fetchCommands(controller.signal)
      .then(res => {
        if (controller.signal.aborted) return
        setCommands(res.commands)
      })
      .catch(() => {})
    return () => controller.abort()
  }, [isOpen, mode, commands, setCommands])

  // Search debounce
  const searchEnabled = isOpen && mode === "search" && input.length >= MIN_QUERY_LENGTH
  useDebouncedSearch(
    input,
    searchEnabled,
    useCallback(
      async (rawQuery, signal) => {
        const trimmed = rawQuery.trim()
        const response = filterGlobalId
          ? await fetchPeople(filterGlobalId, trimmed, signal)
          : await fetchLookup(trimmed, signal)
        if (signal.aborted) return
        const filter = filterGlobalId ? (response as PeopleResponse).filter : null
        setResults(response.results, trimmed, filter)
        // Capture results for tracking — flushed on close or activation.
        const ids = [...response.results.user_results, ...response.results.other_results].map(r => r.id)
        capturePendingTracking({
          query: trimmed,
          resultIds: ids,
          resultCount: ids.length,
          filterGid: filterGlobalId,
        })
      },
      [filterGlobalId, setResults, capturePendingTracking]
    ),
    {
      onLoading: setLoading,
      onTimeout: setTimeoutError,
    }
  )

  // Compute item count for current mode
  const itemCount = useMemo(() => {
    if (mode === "active") return 0
    if (mode === "commands") {
      return commands ? filterCommands(commands, input).length : 0
    }
    if (mode === "search") {
      const total = (results?.user_results.length ?? 0) + (results?.other_results.length ?? 0)
      return total + (query.length >= MIN_QUERY_LENGTH ? 1 : 0) // +1 for see-all footer
    }
    return recent.length
  }, [mode, commands, input, results, query, recent])

  const flushTracking = useCallback(
    (contentId?: string, position?: number) => {
      const pending = consumePendingTracking()
      if (!pending || !pending.query) return
      trackSearch({
        query: pending.query,
        result_count: pending.resultCount,
        result_ids: pending.resultIds,
        filter_author_gid: pending.filterGid ?? undefined,
        ...(contentId !== undefined ? { clicked_content_id: contentId } : {}),
        ...(position !== undefined ? { clicked_position: position } : {}),
      })
    },
    [consumePendingTracking]
  )

  const handleCommandActivate = useCallback(
    (command: Command) => {
      if (command.type === "quick_link" && command.url) {
        if (command.options?.open_in_new_tab) {
          window.open(command.url, "_blank", "noopener,noreferrer")
        } else {
          boostedNavigate(command.url)
        }
        close()
        return
      }
      activateCommand(command.key)
    },
    [activateCommand, close]
  )

  const handleSeeAllActivate = useCallback(() => {
    flushTracking()
    close()
    // The `<a href>` handles navigation; we just flush tracking before unload.
  }, [flushTracking, close])

  // Activation via Enter clicks whichever row is visually selected. Each row
  // tags its interactive element with `data-palette-active` when isSelected,
  // and that element's own onClick + (for anchors) native href navigation does
  // the work — no per-mode switch, no URL duplication.
  const onActivate = useCallback(() => {
    if (mode === "active") return
    document.querySelector<HTMLElement>("[data-palette-active]")?.click()
  }, [mode])

  const { handleArrowDown, handleArrowUp, handleEnter, handleMouseMove, handleItemHover } = useArrowKeySelection({
    itemCount,
    selectedIndex,
    setSelectedIndex,
    onActivate,
    mouseEnabled,
    setMouseEnabled,
    initialMouse,
    setInitialMouse,
  })

  const handleClose = useCallback(() => {
    // Read pendingTracking via getState() — we don't want to re-create this
    // callback every time a search response captures fresh tracking.
    const { pendingTracking, mode: currentMode } = usePaletteStore.getState()
    if (pendingTracking && currentMode === "search") flushTracking()
    close()
  }, [flushTracking, close])

  const handleInputChange = (value: string) => {
    if (value === "/") {
      setMode("commands")
      setInput("")
      return
    }
    if (value === "" && mode === "search") {
      if (filterGlobalId) {
        setInput("")
      } else {
        goToRecent()
      }
      return
    }
    if (value.length > 0 && mode !== "active" && mode !== "commands") {
      setMode("search")
    }
    setInput(value)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    // The active form owns its own keystrokes. While a sub-form is fetching
    // its initial data the palette input still holds focus, so a stray
    // Backspace here would call exitCommand() and dump the user out of the
    // form. Only Escape should reach this handler in active mode.
    if (mode === "active") {
      if (event.key === "Escape") {
        event.stopPropagation()
        exitCommand()
      }
      return
    }
    switch (event.key) {
      case "Escape": {
        event.stopPropagation()
        if (mode === "commands") goToRecent()
        else handleClose()
        return
      }
      case "Backspace":
      case "Delete": {
        if (input === "" && filterGlobalId) {
          event.preventDefault()
          clearFilter()
          if (mode === "search") goToRecent()
        } else if (input === "") {
          event.preventDefault()
          if (mode === "commands") goToRecent()
          else handleClose()
        }
        return
      }
      case "ArrowDown":
        event.preventDefault()
        event.stopPropagation()
        handleArrowDown()
        return
      case "ArrowUp":
        event.preventDefault()
        event.stopPropagation()
        handleArrowUp()
        return
      case "Enter":
        event.preventDefault()
        event.stopPropagation()
        handleEnter()
        return
    }
  }

  const handleEditQuickLink = (command: Command) => {
    if (command.quick_link_id) activateCommand(command.quick_link_id)
  }

  const handleUserActivate = (result: LookupResult) => {
    setFilter(result.global_id)
  }

  const handleResultActivate = (result: LookupResult, index: number) => {
    flushTracking(result.id, index)
    // Since #8903 the anchor navigates via a realm-preserving boosted swap, so the
    // palette no longer tears down on navigation — close it explicitly, like handleSeeAllActivate.
    close()
  }

  const handleClearFilter = () => {
    clearFilter()
    if (mode === "search" && !input) goToRecent()
  }

  const handleBack = () => {
    if (mode === "commands") goToRecent()
    else if (mode === "active") exitCommand()
  }

  // Leave a quick-link sub-form and reclaim focus on the palette input.
  // PaletteInput's own useLayoutEffect refocuses on `mode` changes, but the
  // QuickLinkForm's submit button being torn down can drop focus to <body>
  // between renders. Without an explicit re-focus, keyboard nav escapes to
  // whatever document-level hotkeys are listening (e.g. the mailbox
  // @github/hotkey buttons), highlighting inbox rows.
  const handleQuickLinkExit = (refreshCommands: boolean) => {
    if (refreshCommands) usePaletteStore.setState({ commands: null })
    exitCommand()
    inputRef.current?.focus()
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  const renderBody = () => {
    if (mode === "active") {
      if (activeCommandKey === "research") return <ResearchForm onSuccess={handleClose} />
      if (!activeCommandKey) return null
      // "create_quick_link" → new form; any other key is an existing quick-link UUID.
      const isNew = activeCommandKey === "create_quick_link"
      return (
        <QuickLinkForm
          quickLinkId={isNew ? null : activeCommandKey}
          onSaved={() => handleQuickLinkExit(true)}
          onDeleted={() => handleQuickLinkExit(true)}
        />
      )
    }

    if (mode === "commands") {
      return (
        <CommandsMode
          commands={commands}
          filterInput={input}
          selectedIndex={selectedIndex}
          onSelect={handleItemHover}
          onActivate={handleCommandActivate}
          onEditQuickLink={handleEditQuickLink}
        />
      )
    }

    if (mode === "search") {
      return (
        <SearchMode
          results={results}
          query={query}
          selectedIndex={selectedIndex}
          onSelect={handleItemHover}
          onUserActivate={handleUserActivate}
          onResultActivate={handleResultActivate}
          onSeeAllActivate={handleSeeAllActivate}
        />
      )
    }

    // Recent rows are boosted anchors too, so — like handleResultActivate above — the
    // palette must close itself. Recent items carry no search tracking, so no flush.
    return <RecentMode items={recent} selectedIndex={selectedIndex} onSelect={handleItemHover} onActivate={close} />
  }

  return (
    <PaletteModal isOpen={isOpen} onClose={handleClose} onMouseMove={handleMouseMove} rootRef={rootRef}>
      <PaletteInput
        inputRef={inputRef}
        input={input}
        placeholder={placeholderFor(mode, filterGlobalId !== null)}
        mode={mode}
        filter={filter}
        showLoadingBar={isLoading && !showTimeoutError}
        showTimeoutError={showTimeoutError && isLoading}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        onClearFilter={handleClearFilter}
        onBack={handleBack}
      />
      {renderBody()}
    </PaletteModal>
  )
}
