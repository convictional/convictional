import { expect, test, describe, beforeEach, afterEach } from "vitest"
import { createElement } from "react"
import {
  mountIsland,
  unmountIsland,
  unmountAll,
  activeRoots,
} from "../../../../app/javascript/react/shared/mountIsland"

function createMountPoint(id: string, props: Record<string, unknown> = {}): HTMLElement {
  const el = document.createElement("div")
  el.id = id
  el.dataset.props = JSON.stringify(props)
  document.body.appendChild(el)
  return el
}

describe("mountIsland", () => {
  afterEach(() => {
    unmountAll()
    document.body.innerHTML = ""
  })

  test("mounts a React component into a DOM element and parses props", () => {
    createMountPoint("test-island", { name: "World" })
    let receivedProps: Record<string, unknown> = {}

    mountIsland("test-island", (props) => {
      receivedProps = props
      return createElement("div", null, `Hello ${props.name}`)
    })

    expect(receivedProps).toEqual({ name: "World" })
    expect(activeRoots.has("test-island")).toBe(true)
  })

  test("does nothing when element does not exist", () => {
    mountIsland("nonexistent", () => createElement("div"))
    expect(activeRoots.size).toBe(0)
  })

  test("is idempotent — calling twice for the same ID does not re-mount", () => {
    createMountPoint("idempotent-island")
    let mountCount = 0

    const render = () => {
      mountCount++
      return createElement("div")
    }

    mountIsland("idempotent-island", render)
    mountIsland("idempotent-island", render)
    mountIsland("idempotent-island", render)

    expect(mountCount).toBe(1)
    expect(activeRoots.size).toBe(1)
  })

  test("re-mounts after explicit unmount", () => {
    createMountPoint("remount-island")
    let mountCount = 0

    const render = () => {
      mountCount++
      return createElement("div")
    }

    mountIsland("remount-island", render)
    expect(mountCount).toBe(1)

    unmountIsland("remount-island")
    mountIsland("remount-island", render)
    expect(mountCount).toBe(2)
  })

  test("handles missing data-props gracefully", () => {
    const el = document.createElement("div")
    el.id = "no-props-island"
    document.body.appendChild(el)

    let receivedProps: Record<string, unknown> = {}
    mountIsland("no-props-island", (props) => {
      receivedProps = props
      return createElement("div", null, "No props")
    })

    expect(receivedProps).toEqual({})
    expect(activeRoots.has("no-props-island")).toBe(true)
  })
})

describe("unmountIsland", () => {
  afterEach(() => {
    unmountAll()
    document.body.innerHTML = ""
  })

  test("unmounts a mounted island and removes it from active roots", () => {
    createMountPoint("test-island")
    mountIsland("test-island", () => createElement("div", null, "mounted"))

    expect(activeRoots.has("test-island")).toBe(true)
    unmountIsland("test-island")
    expect(activeRoots.has("test-island")).toBe(false)
  })

  test("does nothing for unknown island id", () => {
    unmountIsland("unknown")
    expect(activeRoots.size).toBe(0)
  })
})

describe("unmountAll", () => {
  afterEach(() => {
    document.body.innerHTML = ""
  })

  test("unmounts all active islands", () => {
    createMountPoint("island-a")
    createMountPoint("island-b")
    mountIsland("island-a", () => createElement("div"))
    mountIsland("island-b", () => createElement("div"))

    expect(activeRoots.size).toBe(2)
    unmountAll()
    expect(activeRoots.size).toBe(0)
  })
})

describe("htmx:beforeSwap cleanup", () => {
  afterEach(() => {
    unmountAll()
    document.body.innerHTML = ""
  })

  test("unmounts islands inside the swap target", () => {
    const container = document.createElement("div")
    container.id = "swap-target"
    document.body.appendChild(container)

    const el = document.createElement("div")
    el.id = "inner-island"
    el.dataset.props = "{}"
    container.appendChild(el)

    mountIsland("inner-island", () => createElement("div"))
    expect(activeRoots.has("inner-island")).toBe(true)

    document.dispatchEvent(
      new CustomEvent("htmx:beforeSwap", { detail: { target: container } })
    )

    expect(activeRoots.has("inner-island")).toBe(false)
  })

  test("unmounts island when swap target IS the island element", () => {
    const el = createMountPoint("direct-target")
    mountIsland("direct-target", () => createElement("div"))

    document.dispatchEvent(
      new CustomEvent("htmx:beforeSwap", { detail: { target: el } })
    )

    expect(activeRoots.has("direct-target")).toBe(false)
  })

  test("does not unmount islands outside the swap target", () => {
    createMountPoint("outside-island")
    mountIsland("outside-island", () => createElement("div"))

    const unrelatedTarget = document.createElement("div")
    document.body.appendChild(unrelatedTarget)

    document.dispatchEvent(
      new CustomEvent("htmx:beforeSwap", { detail: { target: unrelatedTarget } })
    )

    expect(activeRoots.has("outside-island")).toBe(true)
  })
})
