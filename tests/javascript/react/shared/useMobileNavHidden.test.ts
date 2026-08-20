import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { useMobileNavHidden } from "../../../../app/javascript/react/shared/hooks/useMobileNavHidden"

function mountContainer(hidden: boolean) {
  let container = document.getElementById("container")
  if (!container) {
    container = document.createElement("main")
    container.id = "container"
    document.body.appendChild(container)
  }
  if (hidden) {
    container.dataset.mobileNav = "hidden"
  } else {
    delete container.dataset.mobileNav
  }
}

describe("useMobileNavHidden", () => {
  afterEach(() => {
    document.getElementById("container")?.remove()
  })

  test("reads the #container attribute on mount", () => {
    mountContainer(true)
    const { result } = renderHook(() => useMobileNavHidden())
    expect(result.current).toBe(true)
  })

  test("is false without the attribute or without #container", () => {
    const { result, unmount } = renderHook(() => useMobileNavHidden())
    expect(result.current).toBe(false)
    unmount()

    mountContainer(false)
    const { result: withContainer } = renderHook(() => useMobileNavHidden())
    expect(withContainer.current).toBe(false)
  })

  test("re-reads the attribute when a boost navigation settles and on popstate", () => {
    mountContainer(false)
    const { result } = renderHook(() => useMobileNavHidden())
    expect(result.current).toBe(false)

    // Boost navigation to a show page: htmx swaps in a new #container with
    // the attribute, then fires htmx:afterSettle.
    mountContainer(true)
    act(() => {
      document.dispatchEvent(new Event("htmx:afterSettle", { bubbles: true }))
    })
    expect(result.current).toBe(true)

    // Browser back to the index: history restore swaps the attribute away.
    mountContainer(false)
    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate"))
    })
    expect(result.current).toBe(false)
  })
})
