import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { installBfcacheGuard, isLoggedInMarkerPresent } from "../../../app/javascript/shared/bfcacheGuard"

function setCookie(value: string): void {
  Object.defineProperty(document, "cookie", { configurable: true, get: () => value })
}

function firePageshow(persisted: boolean): void {
  const event = new Event("pageshow")
  Object.defineProperty(event, "persisted", { value: persisted })
  window.dispatchEvent(event)
}

describe("isLoggedInMarkerPresent", () => {
  afterEach(() => {
    setCookie("")
  })

  test("matches only an exact logged_in=1 cookie pair", () => {
    setCookie("logged_in=1")
    expect(isLoggedInMarkerPresent()).toBe(true)

    setCookie("foo=bar; logged_in=1; baz=qux")
    expect(isLoggedInMarkerPresent()).toBe(true)

    setCookie("")
    expect(isLoggedInMarkerPresent()).toBe(false)

    // Substring lookalikes must not match.
    setCookie("xlogged_in=1")
    expect(isLoggedInMarkerPresent()).toBe(false)

    setCookie("logged_in=10")
    expect(isLoggedInMarkerPresent()).toBe(false)
  })
})

describe("installBfcacheGuard", () => {
  let reload: ReturnType<typeof vi.fn>
  let uninstall: () => void

  beforeEach(() => {
    reload = vi.fn()
    vi.stubGlobal("location", { reload })
    uninstall = installBfcacheGuard()
  })

  afterEach(() => {
    uninstall()
    vi.unstubAllGlobals()
    setCookie("")
    delete document.body.dataset.authenticated
  })

  test("reloads on a bfcache restore of an authenticated page whose marker is gone", () => {
    document.body.dataset.authenticated = "true"
    setCookie("")

    firePageshow(true)

    expect(reload).toHaveBeenCalledTimes(1)
  })

  test("does not reload on a normal (non-persisted) load", () => {
    document.body.dataset.authenticated = "true"
    setCookie("")

    firePageshow(false)

    expect(reload).not.toHaveBeenCalled()
  })

  test("does not reload when the logged_in marker is still present", () => {
    document.body.dataset.authenticated = "true"
    setCookie("logged_in=1")

    firePageshow(true)

    expect(reload).not.toHaveBeenCalled()
  })

  test("does not reload when the page is not authenticated", () => {
    document.body.dataset.authenticated = "false"
    setCookie("")

    firePageshow(true)

    expect(reload).not.toHaveBeenCalled()
  })
})
