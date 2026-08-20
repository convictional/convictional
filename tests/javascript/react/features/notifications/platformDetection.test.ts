import { afterEach, describe, expect, test, vi } from "vitest"

// jsdom doesn't expose serviceWorker / PushManager / Notification globals, so
// the real isPushSupported is always false here. Mock it to true and isolate
// what we actually want to exercise — the iOS-vs-standalone gating logic.
vi.mock("../../../../../app/javascript/react/features/notifications/pushSubscription", () => ({
  isPushSupported: () => true,
}))

import { isPushAvailableHere, isStandalonePWA } from "../../../../../app/javascript/react/features/notifications/platformDetection"

const IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko)"
const ANDROID_CHROME_UA =
  "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
const DESKTOP_CHROME_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

// jsdom locks navigator.userAgent / platform / maxTouchPoints behind read-only
// getters. Object.defineProperty with `configurable: true` lets us swap them
// per test and put them back in afterEach so cross-test pollution can't happen.
function spoofNavigator({
  userAgent,
  platform,
  maxTouchPoints,
}: {
  userAgent: string
  platform: string
  maxTouchPoints: number
}): void {
  Object.defineProperty(navigator, "userAgent", { value: userAgent, configurable: true })
  Object.defineProperty(navigator, "platform", { value: platform, configurable: true })
  Object.defineProperty(navigator, "maxTouchPoints", { value: maxTouchPoints, configurable: true })
}

function spoofMatchMedia(matches: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  // Reset navigator overrides — leave userAgent etc. in whatever state jsdom
  // had originally so other test files don't see iOS leak in.
  Object.defineProperty(navigator, "userAgent", { value: DESKTOP_CHROME_UA, configurable: true })
  Object.defineProperty(navigator, "platform", { value: "MacIntel", configurable: true })
  Object.defineProperty(navigator, "maxTouchPoints", { value: 0, configurable: true })
  delete (window.navigator as Navigator & { standalone?: boolean }).standalone
})

describe("isStandalonePWA", () => {
  test("returns true when display-mode matches standalone", () => {
    spoofMatchMedia(true)
    expect(isStandalonePWA()).toBe(true)
  })

  test("returns true via the iOS-specific navigator.standalone flag", () => {
    spoofMatchMedia(false)
    ;(window.navigator as Navigator & { standalone?: boolean }).standalone = true
    expect(isStandalonePWA()).toBe(true)
  })

  test("returns false in a regular browser tab", () => {
    spoofMatchMedia(false)
    expect(isStandalonePWA()).toBe(false)
  })
})

describe("isPushAvailableHere", () => {
  test("false on iOS Safari tab (push exists but Apple blocks it)", () => {
    spoofNavigator({ userAgent: IPHONE_UA, platform: "iPhone", maxTouchPoints: 5 })
    spoofMatchMedia(false)
    expect(isPushAvailableHere()).toBe(false)
  })

  test("true on iOS PWA standalone", () => {
    spoofNavigator({ userAgent: IPHONE_UA, platform: "iPhone", maxTouchPoints: 5 })
    spoofMatchMedia(true)
    expect(isPushAvailableHere()).toBe(true)
  })

  test("true on Android Chrome", () => {
    spoofNavigator({ userAgent: ANDROID_CHROME_UA, platform: "Linux armv8l", maxTouchPoints: 5 })
    spoofMatchMedia(false)
    expect(isPushAvailableHere()).toBe(true)
  })

  test("true on desktop Chrome", () => {
    spoofNavigator({ userAgent: DESKTOP_CHROME_UA, platform: "MacIntel", maxTouchPoints: 0 })
    spoofMatchMedia(false)
    expect(isPushAvailableHere()).toBe(true)
  })
})
