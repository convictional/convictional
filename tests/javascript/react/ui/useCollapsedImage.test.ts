import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test } from "vitest"

import { attachmentKey, useCollapsedImage } from "~/react/ui/hooks/useCollapsedImage"

beforeEach(() => window.localStorage.clear())
afterEach(() => window.localStorage.clear())

describe("attachmentKey", () => {
  test("extracts the attachment id from a workspace download URL", () => {
    expect(attachmentKey("/api/workspaces/w1/attachments/abc-123/download")).toBe("abc-123")
  })

  test("extracts the id from the org-wide download URL", () => {
    expect(attachmentKey("/api/workspaces/attachments/xyz-9/download")).toBe("xyz-9")
  })

  test("falls back to the raw src when it isn't an attachment URL", () => {
    expect(attachmentKey("https://example.com/cat.png")).toBe("https://example.com/cat.png")
  })
})

describe("useCollapsedImage", () => {
  test("defaults to expanded and toggles", () => {
    const { result } = renderHook(() => useCollapsedImage("abc-123"))
    expect(result.current[0]).toBe(false)

    act(() => result.current[1]())
    expect(result.current[0]).toBe(true)

    act(() => result.current[1]())
    expect(result.current[0]).toBe(false)
  })

  test("persists collapsed state across remounts under the same id", () => {
    const first = renderHook(() => useCollapsedImage("abc-123"))
    act(() => first.result.current[1]())
    expect(first.result.current[0]).toBe(true)

    // A fresh mount (e.g. after reload) reads the persisted choice.
    const second = renderHook(() => useCollapsedImage("abc-123"))
    expect(second.result.current[0]).toBe(true)

    // A different id is independent.
    const other = renderHook(() => useCollapsedImage("def-456"))
    expect(other.result.current[0]).toBe(false)
  })
})
