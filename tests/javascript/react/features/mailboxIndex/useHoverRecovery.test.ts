import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { useHoverRecovery } from "~/react/features/mailboxIndex/hooks/useHoverRecovery"

// jsdom does no layout, so stub each row's rect (a horizontal band from top→bottom).
function stubRect(element: HTMLElement, top: number, bottom: number) {
  element.getBoundingClientRect = () =>
    ({
      left: 0,
      right: 100,
      top,
      bottom,
      x: 0,
      y: top,
      width: 100,
      height: bottom - top,
      toJSON: () => ({}),
    }) as DOMRect
}

function addRow(container: HTMLElement, id: string, top: number, bottom: number): HTMLElement {
  const element = document.createElement("div")
  element.setAttribute("data-thread-id", id)
  stubRect(element, top, bottom)
  container.appendChild(element)
  return element
}

function movePointer(x: number, y: number) {
  act(() => {
    document.dispatchEvent(new MouseEvent("pointermove", { clientX: x, clientY: y }))
  })
}

afterEach(() => {
  document.body.innerHTML = ""
})

describe("useHoverRecovery", () => {
  test("forces the row that slides under a stationary pointer after the list changes", () => {
    const container = document.createElement("div")
    addRow(container, "a", 0, 50)
    const rowB = addRow(container, "b", 50, 100)
    addRow(container, "c", 100, 150)
    document.body.appendChild(container)

    const ref = { current: container }
    const { result, rerender } = renderHook(({ ids }) => useHoverRecovery(ref, ids), {
      initialProps: { ids: ["a", "b", "c"] },
    })

    // Nothing forced until the pointer has been located and the list shifts.
    expect(result.current).toBeNull()

    // Pointer resting over row A. Normal hover is CSS-driven, so the hook stays quiet.
    movePointer(10, 25)
    expect(result.current).toBeNull()

    // Archive row A: it's removed and row B slides up under the stationary pointer.
    container.querySelector('[data-thread-id="a"]')?.remove()
    stubRect(rowB, 0, 50)
    rerender({ ids: ["b", "c"] })

    expect(result.current).toBe("b")

    // Any real pointer movement hands control back to native :hover.
    movePointer(10, 25)
    expect(result.current).toBeNull()
  })

  test("forces nothing when the pointer is outside every row after a change", () => {
    const container = document.createElement("div")
    addRow(container, "a", 0, 50)
    addRow(container, "b", 50, 100)
    document.body.appendChild(container)

    const ref = { current: container }
    const { result, rerender } = renderHook(({ ids }) => useHoverRecovery(ref, ids), {
      initialProps: { ids: ["a", "b"] },
    })

    movePointer(10, 500) // below the list
    container.querySelector('[data-thread-id="a"]')?.remove()
    rerender({ ids: ["b"] })

    expect(result.current).toBeNull()
  })
})
