import { afterEach, describe, expect, test } from "vitest"

import { isIOS } from "../../../../app/javascript/react/shared/platform"

const IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko)"
const IPAD_OS_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
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

afterEach(() => {
  Object.defineProperty(navigator, "userAgent", { value: DESKTOP_CHROME_UA, configurable: true })
  Object.defineProperty(navigator, "platform", { value: "MacIntel", configurable: true })
  Object.defineProperty(navigator, "maxTouchPoints", { value: 0, configurable: true })
})

describe("isIOS", () => {
  test("returns true for iPhone user agent", () => {
    spoofNavigator({ userAgent: IPHONE_UA, platform: "iPhone", maxTouchPoints: 5 })
    expect(isIOS()).toBe(true)
  })

  test("returns true for iPadOS 13+ (MacIntel with touch)", () => {
    spoofNavigator({ userAgent: IPAD_OS_UA, platform: "MacIntel", maxTouchPoints: 5 })
    expect(isIOS()).toBe(true)
  })

  test("returns false for desktop Mac (MacIntel without touch)", () => {
    spoofNavigator({ userAgent: DESKTOP_CHROME_UA, platform: "MacIntel", maxTouchPoints: 0 })
    expect(isIOS()).toBe(false)
  })

  test("returns false for Android", () => {
    spoofNavigator({ userAgent: ANDROID_CHROME_UA, platform: "Linux armv8l", maxTouchPoints: 5 })
    expect(isIOS()).toBe(false)
  })
})
