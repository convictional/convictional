import { renderHook } from "@testing-library/react"
import { useRef } from "react"
import { EditorState } from "prosemirror-state"
import type { EditorView } from "prosemirror-view"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { useChatEditorHandle, type ChatEditorHandle } from "../../../../../app/javascript/react/composites/editor/features/useChatEditorHandle"
import type { AttachmentsFeature } from "../../../../../app/javascript/react/composites/editor/features/useAttachments"
import type { EnterToSendFeature } from "../../../../../app/javascript/react/composites/editor/features/useEnterToSend"
import { parse, schema } from "../../../../../app/javascript/richText/schema"

// Render the hook with a stable ref + a viewRef pointing at a mocked EditorView,
// and return the imperative handle the hook exposes via useImperativeHandle.
function setup(state: unknown = {}) {
  const view = {
    focus: vi.fn(),
    state,
  } as unknown as EditorView

  const attachments: AttachmentsFeature = {
    plugins: [],
    claimId: "claim-1",
    upload: vi.fn(),
  }

  const enterToSend: EnterToSendFeature = {
    plugins: [],
    send: vi.fn(),
  }

  const { result } = renderHook(() => {
    const handleRef = useRef<ChatEditorHandle>(null)
    const viewRef = useRef<EditorView | null>(view)
    useChatEditorHandle(handleRef, enterToSend, viewRef, attachments)
    return handleRef
  })

  // useImperativeHandle assigns to .current synchronously after render.
  const handle = result.current.current
  if (!handle) throw new Error("ChatEditorHandle was not set on the ref")

  return { handle, view, attachments, enterToSend }
}

describe("useChatEditorHandle — batched upload", () => {
  let appendChildSpy: ReturnType<typeof vi.spyOn>
  let capturedInputs: HTMLInputElement[]

  beforeEach(() => {
    capturedInputs = []
    // Intercept the temp <input> the hook injects when triggerUpload() runs,
    // so the test can drive its change/cancel events deterministically without
    // triggering a real native file picker dialog. We still attach the node so
    // isConnected reflects reality and the hook's cleanup (input.remove()) can
    // flip it back to false.
    appendChildSpy = vi.spyOn(document.body, "appendChild").mockImplementation(((node: Node) => {
      if (node instanceof HTMLInputElement) {
        capturedInputs.push(node)
      }
      return Node.prototype.appendChild.call(document.body, node)
    }) as typeof document.body.appendChild)
  })

  afterEach(() => {
    appendChildSpy.mockRestore()
  })

  test("uploadFiles and triggerUpload dispatch a single batched call to attachments.upload", () => {
    const { handle, view, attachments } = setup()
    const uploadMock = attachments.upload as ReturnType<typeof vi.fn>

    // Part A — uploadFiles forwards all files in one call.
    const a = new File([new Blob(["x"])], "a.png", { type: "image/png" })
    const b = new File([new Blob(["x"])], "b.png", { type: "image/png" })
    const c = new File([new Blob(["x"])], "c.txt", { type: "text/plain" })

    handle.uploadFiles([a, b, c])

    expect(uploadMock).toHaveBeenCalledTimes(1)
    expect(uploadMock).toHaveBeenCalledWith(view, [a, b, c])

    // Part B — triggerUpload creates a <input type=file multiple>, dispatches
    // one batched upload on change, and cleans up the input afterwards.
    uploadMock.mockClear()
    handle.triggerUpload()

    expect(capturedInputs).toHaveLength(1)
    const input = capturedInputs[0]!
    expect(input.type).toBe("file")
    expect(input.multiple).toBe(true)
    expect(input.isConnected).toBe(true)

    // jsdom's HTMLInputElement.files is read-only; stub it so the onchange handler
    // sees the three files we want to "select".
    const fileList = {
      length: 3,
      0: a,
      1: b,
      2: c,
      item(i: number) {
        return [a, b, c][i] ?? null
      },
      [Symbol.iterator]: function* () {
        yield a
        yield b
        yield c
      },
    } as unknown as FileList
    Object.defineProperty(input, "files", { value: fileList, configurable: true })

    input.dispatchEvent(new Event("change"))

    expect(uploadMock).toHaveBeenCalledTimes(1)
    expect(uploadMock).toHaveBeenCalledWith(view, [a, b, c])
    expect(input.isConnected).toBe(false)

    // Part C — cancel path: a fresh triggerUpload that the user dismisses
    // (no file selected) cleans up the input and does NOT call upload.
    uploadMock.mockClear()
    handle.triggerUpload()

    expect(capturedInputs).toHaveLength(2)
    const cancelInput = capturedInputs[1]!
    expect(cancelInput.isConnected).toBe(true)

    cancelInput.dispatchEvent(new Event("cancel"))

    expect(cancelInput.isConnected).toBe(false)
    expect(uploadMock).not.toHaveBeenCalled()

    // Part D — zero-files change event: the input's onchange fires with no
    // files selected (input.files is empty/null). The `if (input.files?.length)`
    // guard must skip the upload call, but cleanup still runs.
    uploadMock.mockClear()
    handle.triggerUpload()

    expect(capturedInputs).toHaveLength(3)
    const emptyInput = capturedInputs[2]!
    expect(emptyInput.isConnected).toBe(true)

    // Do not assign anything to emptyInput.files — it stays as the default
    // (null/empty FileList in jsdom), exercising the guard.
    emptyInput.dispatchEvent(new Event("change"))

    expect(uploadMock).not.toHaveBeenCalled()
    expect(emptyInput.isConnected).toBe(false)
  })
})

describe("useChatEditorHandle — getReferencedAttachmentIds", () => {
  const ID_IMAGE = "11111111-1111-1111-1111-111111111111"
  const ID_FILE = "22222222-2222-2222-2222-222222222222"
  const attachmentUrl = (id: string) => `https://app.example.com/workspaces/attachments/${id}/download`

  test("collects ids from both inline images and non-image file links", () => {
    const markdown =
      `![pic](${attachmentUrl(ID_IMAGE)}) ` +
      `[report.pdf](${attachmentUrl(ID_FILE)}) ` +
      `[external](https://example.com)`
    const { handle } = setup(EditorState.create({ schema, doc: parse(markdown) }))

    expect(handle.getReferencedAttachmentIds().sort()).toEqual([ID_IMAGE, ID_FILE].sort())
  })

  test("drops a file whose link was removed from the doc", () => {
    const { handle } = setup(EditorState.create({ schema, doc: parse("just text, no attachments") }))

    expect(handle.getReferencedAttachmentIds()).toEqual([])
  })
})
