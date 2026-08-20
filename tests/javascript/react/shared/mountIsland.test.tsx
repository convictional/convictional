import { act } from "react"
import { afterEach, describe, expect, it } from "vitest"

import { activeRoots, mountIsland, pruneDetachedRoots, unmountAll } from "~/react/shared/mountIsland"

// Flush the removal MutationObserver (delivered on a microtask) and the rAF it
// schedules, so the observer-driven prune has run by the time we assert.
async function flushRemovalObserver() {
  await Promise.resolve()
  await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
  await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
}

function addHost(id: string): HTMLElement {
  const el = document.createElement("div")
  el.id = id
  document.body.appendChild(el)
  return el
}

afterEach(() => {
  act(() => unmountAll())
  document.body.innerHTML = ""
})

describe("mountIsland", () => {
  it("mounts into the host element and registers the root", () => {
    const host = addHost("react-test-a")
    act(() => mountIsland("react-test-a", () => <div>island-a</div>))

    expect(activeRoots.has("react-test-a")).toBe(true)
    expect(host.textContent).toBe("island-a")
  })

  it("is idempotent while the host stays connected", () => {
    addHost("react-test-b")
    act(() => mountIsland("react-test-b", () => <div>island-b</div>))
    const first = activeRoots.get("react-test-b")?.root

    act(() => mountIsland("react-test-b", () => <div>island-b</div>))
    expect(activeRoots.get("react-test-b")?.root).toBe(first)
  })

  it("does not prune a root whose host is still connected", () => {
    addHost("react-test-c")
    act(() => mountIsland("react-test-c", () => <div>island-c</div>))

    act(() => pruneDetachedRoots())
    expect(activeRoots.has("react-test-c")).toBe(true)
  })

  it("prunes a root once its host is removed from the document", () => {
    const host = addHost("react-test-d")
    act(() => mountIsland("react-test-d", () => <div>island-d</div>))
    expect(activeRoots.has("react-test-d")).toBe(true)

    host.remove()
    act(() => pruneDetachedRoots())
    expect(activeRoots.has("react-test-d")).toBe(false)
  })

  it("prunes a root once an ancestor of its host is removed", () => {
    const wrapper = document.createElement("div")
    document.body.appendChild(wrapper)
    const host = document.createElement("div")
    host.id = "react-test-f"
    wrapper.appendChild(host)

    act(() => mountIsland("react-test-f", () => <div>island-f</div>))
    expect(activeRoots.has("react-test-f")).toBe(true)

    // The host leaves the document via its ancestor, not directly — isConnected
    // still reports false, so the prune must catch it (React parent re-renders).
    wrapper.remove()
    act(() => pruneDetachedRoots())
    expect(activeRoots.has("react-test-f")).toBe(false)
  })

  it("auto-prunes via the removal observer when a host is removed with no htmx swap", async () => {
    const host = addHost("react-test-e")
    act(() => mountIsland("react-test-e", () => <div>island-e</div>))
    expect(activeRoots.has("react-test-e")).toBe(true)

    // A plain DOM removal — the path React re-renders and SPA routing take,
    // with no htmx:beforeSwap. The observer must still tear the root down.
    host.remove()
    await act(async () => {
      await flushRemovalObserver()
    })

    expect(activeRoots.has("react-test-e")).toBe(false)
  })
})
