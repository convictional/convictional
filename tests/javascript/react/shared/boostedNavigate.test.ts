import { afterEach, beforeEach, describe, expect, it, type Mock, vi } from "vitest"

import { boostedNavigate } from "~/react/shared/boostedNavigate"

interface WindowWithHtmx {
  htmx?: { process: (el: Element) => void }
}

// jsdom's window.location can't be navigated or spied directly, so swap in a
// stub exposing just what boostedNavigate reads (origin) and writes (href),
// then restore it.
const realLocation = window.location
const origin = realLocation.origin
let hrefSpy: Mock<(url: string) => void>

beforeEach(() => {
  hrefSpy = vi.fn<(url: string) => void>()
  Object.defineProperty(window, "location", {
    configurable: true,
    value: Object.defineProperty({ origin }, "href", { set: hrefSpy }),
  })
})

afterEach(() => {
  Object.defineProperty(window, "location", { configurable: true, value: realLocation })
  vi.restoreAllMocks()
  delete (window as unknown as WindowWithHtmx).htmx
})

describe("boostedNavigate", () => {
  it("boosts a same-origin navigation via a synthesized anchor when htmx is present", () => {
    const process = vi.fn()
    ;(window as unknown as WindowWithHtmx).htmx = { process }
    // Mock the anchor click so jsdom doesn't attempt a real navigation.
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})

    boostedNavigate("/chats/123")

    expect(process).toHaveBeenCalledOnce()
    const processed = process.mock.calls[0][0] as HTMLAnchorElement
    expect(processed.tagName).toBe("A")
    expect(processed.getAttribute("href")).toBe("/chats/123")
    expect(click).toHaveBeenCalledOnce()
    expect(hrefSpy).not.toHaveBeenCalled()
    // The synthesized anchor is removed after the click.
    expect(document.querySelector('a[href="/chats/123"]')).toBeNull()
  })

  it("falls back to a full-document navigation for cross-origin urls", () => {
    const process = vi.fn()
    ;(window as unknown as WindowWithHtmx).htmx = { process }

    boostedNavigate("https://meet.google.com/abc-defg-hij")

    expect(hrefSpy).toHaveBeenCalledWith("https://meet.google.com/abc-defg-hij")
    expect(process).not.toHaveBeenCalled()
  })

  it("falls back to a full-document navigation when htmx is absent (SPA shell)", () => {
    boostedNavigate("/goals")

    expect(hrefSpy).toHaveBeenCalledWith("/goals")
  })
})
