import { beforeEach, describe, expect, test } from "vitest"

// Importing the mount module registers the window-event bridge as a side effect.
import "~/react/composites/toaster/mount"
import { toastStore } from "~/react/shared/stores/toast"
import { showFlash } from "~/shared/flash"

beforeEach(() => {
  toastStore.setState({ toasts: [] })
})

describe("showFlash → toast store bridge", () => {
  test("dispatches a toast the store picks up, preserving level/url/persistent", () => {
    showFlash("Heads up", "error", "https://example.test/reload", true)

    const { toasts } = toastStore.getState()
    expect(toasts).toHaveLength(1)
    expect(toasts[0]).toMatchObject({
      message: "Heads up",
      level: "error",
      url: "https://example.test/reload",
      persistent: true,
    })
  })

  test("defaults: error level, non-persistent, no url", () => {
    showFlash("Something failed")

    expect(toastStore.getState().toasts[0]).toMatchObject({
      message: "Something failed",
      level: "error",
      persistent: false,
    })
    expect(toastStore.getState().toasts[0].url).toBeUndefined()
  })
})
