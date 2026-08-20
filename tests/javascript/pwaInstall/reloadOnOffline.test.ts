import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { reloadOnOffline } from "../../../app/javascript/pwaInstall/reloadOnOffline"

describe("reloadOnOffline", () => {
  let reload: ReturnType<typeof vi.fn>

  beforeEach(() => {
    reload = vi.fn()
    // jsdom's `location.reload` is non-configurable on Location.prototype, so
    // we replace `window.location` wholesale with a minimal stub. The handler
    // only reads `location.reload`, so this is enough surface area.
    vi.stubGlobal("location", { reload })

    reloadOnOffline()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function setOnline(online: boolean) {
    Object.defineProperty(navigator, "onLine", {
      configurable: true,
      get: () => online,
    })
  }

  test("reloads the page when htmx:sendError fires while offline", () => {
    setOnline(false)

    document.dispatchEvent(new CustomEvent("htmx:sendError"))

    expect(reload).toHaveBeenCalledTimes(1)
  })

  test("does not reload when htmx:sendError fires while online", () => {
    setOnline(true)

    document.dispatchEvent(new CustomEvent("htmx:sendError"))

    expect(reload).not.toHaveBeenCalled()
  })

  test("ignores other htmx events even when offline", () => {
    setOnline(false)

    // `htmx:responseError` is for HTTP error responses (e.g. 5xx) — a real
    // server reply, not a network failure — so we explicitly don't reload.
    document.dispatchEvent(new CustomEvent("htmx:responseError"))
    document.dispatchEvent(new CustomEvent("htmx:beforeRequest"))

    expect(reload).not.toHaveBeenCalled()
  })
})
