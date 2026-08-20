import { describe, expect, test } from "vitest"

import { resolveShellWidth, shellWidthClassName } from "~/react/app/shellWidth"

describe("resolveShellWidth", () => {
  test("defaults to narrow when no match declares a width", () => {
    expect(resolveShellWidth([])).toBe("narrow")
    expect(resolveShellWidth([{ staticData: {} }, { staticData: {} }])).toBe("narrow")
  })

  test("the deepest match with an explicit width wins", () => {
    const matches = [{ staticData: { shellWidth: "medium" as const } }, { staticData: { shellWidth: "full" as const } }]
    expect(resolveShellWidth(matches)).toBe("full")
  })

  test("a leaf without a width falls back to a parent's width", () => {
    const matches = [{ staticData: { shellWidth: "full" as const } }, { staticData: {} }]
    expect(resolveShellWidth(matches)).toBe("full")
  })
})

describe("shellWidthClassName", () => {
  test("maps each width to its container classes, mirroring the Jinja wrapper map", () => {
    // Full-width pages stay edge-to-edge with no top gap. Narrow/medium carry
    // the `page-content` marker so main.css supplies the top gap below the nav
    // (sticky-header pages opt out of it via :has()); the top gap is no longer a
    // pt-* utility on the wrapper itself.
    expect(shellWidthClassName("full")).toBe("w-full")
    expect(shellWidthClassName("medium")).toBe("page-content w-full max-w-screen-xl mx-auto pb-12")
    expect(shellWidthClassName("narrow")).toBe("page-content w-full max-w-4xl mx-auto pb-12")
  })
})
