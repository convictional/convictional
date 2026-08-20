import { beforeEach, describe, expect, test } from "vitest"

import { usePaletteStore } from "../../../../../app/javascript/react/features/commandPalette/store"

function reset() {
  usePaletteStore.setState({
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
  })
}

beforeEach(reset)

describe("palette store", () => {
  test("open() resets state and dispatches event", () => {
    let opened = false
    const handler = () => {
      opened = true
    }
    window.addEventListener("command-palette:opened", handler)

    usePaletteStore.setState({ commands: [] }) // commands survive open()
    usePaletteStore.getState().open()

    expect(usePaletteStore.getState().isOpen).toBe(true)
    expect(usePaletteStore.getState().mode).toBe("recent")
    expect(usePaletteStore.getState().commands).toEqual([])
    expect(opened).toBe(true)
    window.removeEventListener("command-palette:opened", handler)
  })

  test("close() resets state and dispatches event", () => {
    let closed = false
    const handler = () => {
      closed = true
    }
    window.addEventListener("command-palette:closed", handler)

    usePaletteStore.getState().open()
    usePaletteStore.getState().close()

    expect(usePaletteStore.getState().isOpen).toBe(false)
    expect(usePaletteStore.getState().input).toBe("")
    expect(closed).toBe(true)
    window.removeEventListener("command-palette:closed", handler)
  })

  test("toggle() flips isOpen", () => {
    const { toggle } = usePaletteStore.getState()
    toggle()
    expect(usePaletteStore.getState().isOpen).toBe(true)
    toggle()
    expect(usePaletteStore.getState().isOpen).toBe(false)
  })

  test("setInput skips case-only changes from iOS auto-cap", () => {
    const { setInput } = usePaletteStore.getState()
    setInput("roger")
    usePaletteStore.setState({ mouseEnabled: true })
    setInput("Roger") // case-only change — should not flip mouseEnabled
    expect(usePaletteStore.getState().mouseEnabled).toBe(true)
    expect(usePaletteStore.getState().input).toBe("Roger")
  })

  test("setInput on real change resets mouseEnabled", () => {
    const { setInput } = usePaletteStore.getState()
    usePaletteStore.setState({ mouseEnabled: true, lastHandledInput: "abc" })
    setInput("abcd")
    expect(usePaletteStore.getState().mouseEnabled).toBe(false)
  })

  test("setFilter switches to search mode and clears input", () => {
    usePaletteStore.setState({ mode: "recent", input: "hi" })
    usePaletteStore.getState().setFilter("gid:user:abc")
    const state = usePaletteStore.getState()
    expect(state.filterGlobalId).toBe("gid:user:abc")
    expect(state.input).toBe("")
    expect(state.mode).toBe("search")
  })

  test("clearFilter resets filter state", () => {
    usePaletteStore.setState({ filterGlobalId: "gid", filter: { kind: "user" } as never })
    usePaletteStore.getState().clearFilter()
    expect(usePaletteStore.getState().filterGlobalId).toBeNull()
    expect(usePaletteStore.getState().filter).toBeNull()
  })

  test("activateCommand → exitCommand round trip", () => {
    usePaletteStore.getState().activateCommand("research")
    expect(usePaletteStore.getState().mode).toBe("active")
    expect(usePaletteStore.getState().activeCommandKey).toBe("research")
    usePaletteStore.getState().exitCommand()
    expect(usePaletteStore.getState().mode).toBe("commands")
    expect(usePaletteStore.getState().activeCommandKey).toBeNull()
  })

  test("goToRecent clears search state", () => {
    usePaletteStore.setState({ mode: "search", query: "test", input: "test" })
    usePaletteStore.getState().goToRecent()
    expect(usePaletteStore.getState().mode).toBe("recent")
    expect(usePaletteStore.getState().input).toBe("")
    expect(usePaletteStore.getState().query).toBe("")
    expect(usePaletteStore.getState().results).toBeNull()
  })

  test("capture + consume pending tracking", () => {
    const tracking = { query: "q", resultIds: ["a"], resultCount: 1, filterGid: null }
    usePaletteStore.getState().capturePendingTracking(tracking)
    expect(usePaletteStore.getState().pendingTracking).toEqual(tracking)
    expect(usePaletteStore.getState().consumePendingTracking()).toEqual(tracking)
    expect(usePaletteStore.getState().pendingTracking).toBeNull()
    expect(usePaletteStore.getState().consumePendingTracking()).toBeNull()
  })
})
