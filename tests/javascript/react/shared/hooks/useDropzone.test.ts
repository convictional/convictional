import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { useDropzone } from "~/react/shared/hooks/useDropzone"

// jsdom has no DragEvent; forge a plain Event carrying a dataTransfer whose
// `types` includes "Files" (the signal the hook uses to react to file drags).
function fileDragEvent(type: string, files: File[] = []) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.defineProperty(event, "dataTransfer", {
    value: { types: ["Files"], files, dropEffect: "" },
  })
  return event
}

afterEach(() => {
  vi.useRealTimers()
})

describe("useDropzone", () => {
  test("shows drag state and forwards dropped files when enabled", () => {
    const onFiles = vi.fn()
    const { result } = renderHook(() => useDropzone({ onFiles }))

    const el = document.createElement("div")
    act(() => result.current.ref(el))

    act(() => {
      el.dispatchEvent(fileDragEvent("dragover"))
    })
    expect(result.current.isDragOver).toBe(true)

    const file = new File(["hi"], "note.txt", { type: "text/plain" })
    act(() => {
      el.dispatchEvent(fileDragEvent("drop", [file]))
    })
    expect(result.current.isDragOver).toBe(false)
    expect(onFiles).toHaveBeenCalledWith([file])
  })

  test("is inert when disabled: no drag overlay, no file handoff", () => {
    const onFiles = vi.fn()
    const { result } = renderHook(() => useDropzone({ onFiles, enabled: false }))

    const el = document.createElement("div")
    act(() => result.current.ref(el))

    const file = new File(["hi"], "note.txt", { type: "text/plain" })
    act(() => {
      el.dispatchEvent(fileDragEvent("dragover"))
      el.dispatchEvent(fileDragEvent("drop", [file]))
    })

    expect(result.current.isDragOver).toBe(false)
    expect(onFiles).not.toHaveBeenCalled()
  })
})
