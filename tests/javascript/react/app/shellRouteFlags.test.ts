import { describe, expect, test } from "vitest"

import {
  resolveClipContainerOverflowX,
  resolveHideMobileNav,
  resolveShowGmailReauthBadge,
} from "~/react/app/shellRouteFlags"

// The three flag resolvers share one shape: false unless some matched route in
// the chain opts in. One table drives all of them.
describe.each([
  ["resolveClipContainerOverflowX", resolveClipContainerOverflowX, "clipContainerOverflowX"] as const,
  ["resolveHideMobileNav", resolveHideMobileNav, "hideMobileNav"] as const,
  ["resolveShowGmailReauthBadge", resolveShowGmailReauthBadge, "showGmailReauthBadge"] as const,
])("%s", (_name, resolve, flag) => {
  test("is false when no matched route opts in", () => {
    expect(resolve([])).toBe(false)
    expect(resolve([{ staticData: {} }, { staticData: {} }])).toBe(false)
  })

  test("is true when any matched route in the chain opts in", () => {
    expect(resolve([{ staticData: {} }, { staticData: { [flag]: true } }])).toBe(true)
  })
})
