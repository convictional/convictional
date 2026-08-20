import { create } from "zustand"

import type { Command, FilterMeta, LookupResults, Mode, RecentItem } from "./types"

export interface PendingTracking {
  query: string
  resultIds: string[]
  resultCount: number
  filterGid: string | null
}

export interface PaletteState {
  isOpen: boolean
  mode: Mode
  input: string
  selectedIndex: number
  filterGlobalId: string | null
  activeCommandKey: string | null

  // search
  query: string
  results: LookupResults | null
  filter: FilterMeta | null

  // recent
  recent: RecentItem[]

  // loading
  isLoading: boolean
  showTimeoutError: boolean

  // mouse-gate (>10px before hover takes over)
  mouseEnabled: boolean
  initialMouse: { x: number; y: number } | null

  // tracking — flushed on close or activation
  pendingTracking: PendingTracking | null

  // commands — fetched lazily on first commands-mode entry
  commands: Command[] | null

  // iOS auto-capitalization de-dup (palette.ts:208-212)
  lastHandledInput: string
}

export interface PaletteActions {
  open: () => void
  close: () => void
  toggle: () => void
  setInput: (value: string) => void
  setMode: (mode: Mode) => void
  setSelectedIndex: (index: number) => void
  setResults: (results: LookupResults, query: string, filter: FilterMeta | null) => void
  setRecent: (items: RecentItem[]) => void
  setCommands: (commands: Command[]) => void
  setLoading: (loading: boolean) => void
  setTimeoutError: (showError: boolean) => void
  setMouseEnabled: (enabled: boolean) => void
  setInitialMouse: (pos: { x: number; y: number } | null) => void
  setFilter: (gid: string) => void
  clearFilter: () => void
  activateCommand: (key: string) => void
  exitCommand: () => void
  goToRecent: () => void
  capturePendingTracking: (tracking: PendingTracking) => void
  consumePendingTracking: () => PendingTracking | null
}

export type PaletteStore = PaletteState & PaletteActions

const INITIAL_STATE: PaletteState = {
  isOpen: false,
  mode: "recent",
  input: "",
  selectedIndex: 0,
  filterGlobalId: null,
  activeCommandKey: null,
  query: "",
  results: null,
  filter: null,
  recent: [],
  isLoading: false,
  showTimeoutError: false,
  mouseEnabled: false,
  initialMouse: null,
  pendingTracking: null,
  commands: null,
  lastHandledInput: "",
}

function dispatch(name: string): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(name))
  }
}

export const usePaletteStore = create<PaletteStore>((set, get) => ({
  ...INITIAL_STATE,

  open: () => {
    if (get().isOpen) return
    set({
      ...INITIAL_STATE,
      isOpen: true,
      commands: get().commands,
    })
    dispatch("command-palette:opened")
  },

  close: () => {
    if (!get().isOpen) return
    set({ ...INITIAL_STATE, commands: get().commands })
    dispatch("command-palette:closed")
  },

  toggle: () => {
    if (get().isOpen) get().close()
    else get().open()
  },

  setInput: (value: string) => {
    // Skip case-only changes (palette.ts:208-212) — Safari/iOS auto-cap can
    // fire a duplicate input event with only the first letter changed.
    const previous = get().lastHandledInput
    if (value.toLowerCase() === previous.toLowerCase() && value !== previous) {
      set({ input: value, lastHandledInput: value })
      return
    }
    set({ input: value, lastHandledInput: value, mouseEnabled: false })
  },

  setMode: (mode: Mode) => set({ mode, selectedIndex: 0 }),

  setSelectedIndex: (index: number) => set({ selectedIndex: index }),

  setResults: (results, query, filter) =>
    set({
      results,
      query,
      filter,
      selectedIndex: 0,
      isLoading: false,
      showTimeoutError: false,
    }),

  setRecent: items => set({ recent: items, selectedIndex: 0 }),

  setCommands: commands => set({ commands }),

  setLoading: loading => set({ isLoading: loading }),

  setTimeoutError: showError => set({ showTimeoutError: showError }),

  setMouseEnabled: enabled => set({ mouseEnabled: enabled }),

  setInitialMouse: pos => set({ initialMouse: pos }),

  setFilter: (gid: string) => {
    set({
      filterGlobalId: gid,
      filter: null,
      input: "",
      lastHandledInput: "",
      selectedIndex: 0,
      mode: "search",
      results: null,
    })
  },

  clearFilter: () => {
    set({
      filterGlobalId: null,
      filter: null,
      selectedIndex: 0,
    })
  },

  activateCommand: (key: string) => {
    set({
      mode: "active",
      activeCommandKey: key,
      input: `/${key}`,
      selectedIndex: 0,
    })
  },

  exitCommand: () => {
    set({
      mode: "commands",
      activeCommandKey: null,
      input: "",
      lastHandledInput: "",
      selectedIndex: 0,
    })
  },

  goToRecent: () => {
    set({
      mode: "recent",
      input: "",
      lastHandledInput: "",
      selectedIndex: 0,
      results: null,
      query: "",
    })
  },

  capturePendingTracking: tracking => set({ pendingTracking: tracking }),

  consumePendingTracking: () => {
    const current = get().pendingTracking
    set({ pendingTracking: null })
    return current
  },
}))
