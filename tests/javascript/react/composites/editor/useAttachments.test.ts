import type { EditorView } from "prosemirror-view"
import { renderHook } from "@testing-library/react"
import { describe, expect, test, vi } from "vitest"

import {
  type AttachmentsFeature,
  openFilePickerAndUpload,
  uploadFilesToView,
  useAttachments,
} from "~/react/composites/editor/features/useAttachments"

function makeAttachments(overrides: Partial<AttachmentsFeature> = {}): AttachmentsFeature {
  return { plugins: [], claimId: "claim-1", upload: vi.fn(), hasUploads: false, ...overrides }
}

function makeView() {
  return { focus: vi.fn() } as unknown as EditorView
}

describe("useAttachments", () => {
  test("yields a no-op feature (empty plugins, silent upload) when uploadUrl is null", () => {
    const { result } = renderHook(() => useAttachments({ uploadUrl: null }))

    expect(result.current.plugins).toEqual([])
    // upload must be safe to call even though nothing is wired.
    expect(() => result.current.upload(makeView(), [new File(["x"], "x.png")])).not.toThrow()
  })

  test("installs the attachments plugin when uploadUrl is provided", () => {
    const { result } = renderHook(() => useAttachments({ uploadUrl: "/upload" }))

    expect(result.current.plugins).toHaveLength(1)
  })
})

describe("uploadFilesToView", () => {
  test("focuses the view before handing files to the feature", () => {
    const view = makeView()
    const attachments = makeAttachments()
    const files = [new File(["x"], "x.png")]

    uploadFilesToView(view, attachments, files)

    expect(view.focus).toHaveBeenCalled()
    expect(attachments.upload).toHaveBeenCalledWith(view, files)
  })

  test("is a no-op when the view is null", () => {
    const attachments = makeAttachments()
    uploadFilesToView(null, attachments, [new File(["x"], "x.png")])
    expect(attachments.upload).not.toHaveBeenCalled()
  })
})

describe("openFilePickerAndUpload", () => {
  test("opens an unfiltered multi-file picker and uploads the chosen files", () => {
    const view = makeView()
    const attachments = makeAttachments()
    const clickSpy = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {})

    openFilePickerAndUpload(view, attachments)

    const input = document.body.querySelector("input[type=file]") as HTMLInputElement
    expect(input).not.toBeNull()
    expect(input.multiple).toBe(true)
    // No `accept` filter: the picker accepts any file type, matching the drop
    // path (images render inline, other files become links).
    expect(input.accept).toBe("")
    expect(clickSpy).toHaveBeenCalled()

    const file = new File(["x"], "x.png", { type: "image/png" })
    Object.defineProperty(input, "files", { value: [file], configurable: true })
    input.dispatchEvent(new Event("change"))

    expect(view.focus).toHaveBeenCalled()
    expect(attachments.upload).toHaveBeenCalledWith(view, [file])
    // The transient input is removed after the picker resolves (Safari-safe cleanup).
    expect(document.body.querySelector("input[type=file]")).toBeNull()

    clickSpy.mockRestore()
  })

  test("removes the input and uploads nothing when the picker is cancelled", () => {
    const view = makeView()
    const attachments = makeAttachments()
    vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {})

    openFilePickerAndUpload(view, attachments)

    const input = document.body.querySelector("input[type=file]") as HTMLInputElement
    input.dispatchEvent(new Event("cancel"))

    expect(attachments.upload).not.toHaveBeenCalled()
    expect(document.body.querySelector("input[type=file]")).toBeNull()

    vi.restoreAllMocks()
  })
})
