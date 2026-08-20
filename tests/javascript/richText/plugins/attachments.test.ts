import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { EditorState, TextSelection } from "prosemirror-state"
import { EditorView, DecorationSet } from "prosemirror-view"

// Mock fetchWithCSRF before importing the plugin (which imports it). The plugin
// imports from "~/shared/csrf", which the Vitest alias resolves to
// app/javascript/shared/csrf.
vi.mock("~/shared/csrf", () => ({
  fetchWithCSRF: vi.fn(),
}))

// Mock showFlash so we can assert the plugin surfaces upload failures to the
// user (and does NOT toast on success).
vi.mock("~/shared/flash", () => ({
  showFlash: vi.fn(),
}))

import { fetchWithCSRF } from "~/shared/csrf"
import { showFlash } from "~/shared/flash"
import getAttachmentsPlugin from "../../../../app/javascript/richText/plugins/attachments"
import { schema, serialize } from "../../../../app/javascript/richText/schema"

const mockFetch = vi.mocked(fetchWithCSRF)
const mockShowFlash = vi.mocked(showFlash)

// Let the fetch → json → dispatch chain inside the plugin's upload routine settle
// before we make assertions. A macrotask tick drains the whole microtask chain,
// including the extra hop where the error path reads the response body.
async function flushMicrotasks() {
  await new Promise(resolve => setTimeout(resolve, 0))
}

// Build a minimal real EditorView wired to the attachments plugin so handleDrop/
// handlePaste props and the dispatched transactions exercise actual ProseMirror code paths.
function createEditor() {
  const container = document.createElement("div")
  document.body.appendChild(container)
  const plugin = getAttachmentsPlugin("/upload", "claim-1")
  const doc = schema.node("doc", null, [schema.node("paragraph")])
  const state = EditorState.create({ doc, schema, plugins: [plugin] })
  const view = new EditorView(container, { state })
  return { view, plugin, container }
}

// Collect the set of files & claim_id present in a FormData payload so assertions
// can inspect what the plugin actually sent.
function inspectFormData(formData: FormData): { files: File[]; claimId: string | null } {
  const files: File[] = []
  let claimId: string | null = null
  formData.forEach((value, key) => {
    if (key === "files" && value instanceof File) {
      files.push(value)
    } else if (key === "claim_id" && typeof value === "string") {
      claimId = value
    }
  })
  return { files, claimId }
}

function makeImageFile(name: string): File {
  return new File([new Blob(["x"])], name, { type: "image/png" })
}

function makeTextFile(name: string): File {
  return new File([new Blob(["x"])], name, { type: "text/plain" })
}

// Convenience: pull the exposed upload function off the plugin spec.
function getUpload(plugin: ReturnType<typeof getAttachmentsPlugin>) {
  return (plugin.spec as unknown as { upload: (v: EditorView, f: File[]) => void }).upload
}

// Count decorations the plugin is currently tracking in editor state.
function decorationCount(view: EditorView, plugin: ReturnType<typeof getAttachmentsPlugin>): number {
  const set = plugin.getState(view.state) as DecorationSet | undefined
  if (!set) return 0
  return set.find().length
}

// Collect inline nodes (text + atom nodes) inside the single top-level paragraph
// so we can assert the order and attrs of inserted attachments.
function inlineChildren(view: EditorView): Array<{ type: string; text: string | null; attrs: Record<string, unknown>; href: string | null }> {
  const out: Array<{ type: string; text: string | null; attrs: Record<string, unknown>; href: string | null }> = []
  view.state.doc.descendants(node => {
    if (node.isBlock) return true
    const linkMark = node.marks.find(mark => mark.type.name === "link")
    out.push({
      type: node.type.name,
      text: node.isText ? (node.text ?? "") : null,
      attrs: { ...node.attrs },
      href: linkMark ? (linkMark.attrs.href as string) : null,
    })
    return false
  })
  return out
}

describe("attachments plugin — batched multi-file upload", () => {
  let editor: ReturnType<typeof createEditor>

  beforeEach(() => {
    mockFetch.mockReset()
    mockShowFlash.mockReset()
    editor = createEditor()
  })

  afterEach(() => {
    editor.view.destroy()
    editor.container.remove()
  })

  test("upload batches N files into one request with N placeholders, then replaces in order", async () => {
    // Hold the fetch in pending state so we can assert pre-resolution state first
    // (one batched call + N placeholders), then resolve and assert insertion.
    let resolveFetch!: (response: Response) => void
    const pending = new Promise<Response>(resolve => {
      resolveFetch = resolve
    })
    mockFetch.mockReturnValueOnce(pending)

    const imgA = makeImageFile("a.png")
    const txtB = makeTextFile("b.txt")
    const txtC = makeTextFile("c.txt")

    const upload = getUpload(editor.plugin)
    upload(editor.view, [imgA, txtB, txtC])

    // Exactly ONE network request was made — not one per file.
    expect(mockFetch).toHaveBeenCalledTimes(1)
    const [url, init] = mockFetch.mock.calls[0]!
    expect(url).toBe("/upload")
    expect(init?.method).toBe("POST")
    expect(init?.body).toBeInstanceOf(FormData)
    const { files, claimId } = inspectFormData(init!.body as FormData)
    expect(files).toHaveLength(3)
    expect(files.map(f => f.name)).toEqual(["a.png", "b.txt", "c.txt"])
    expect(claimId).toBe("claim-1")

    // Three placeholders rendered while we wait for the response.
    expect(decorationCount(editor.view, editor.plugin)).toBe(3)

    // Now resolve the batch with three attachment URLs, in order.
    resolveFetch({
      ok: true,
      json: () =>
        Promise.resolve({
          attachments: [{ download_url: "/a" }, { download_url: "/b" }, { download_url: "/c" }],
        }),
    } as unknown as Response)
    await flushMicrotasks()

    // Document contains: image, link("b.txt"), " ", link("c.txt"), " ".
    // The trailing space after each non-image link prevents adjacent filenames
    // from concatenating (e.g. "b.txtc.txt").
    const inline = inlineChildren(editor.view)
    expect(inline).toHaveLength(5)
    expect(inline[0]!.type).toBe("image")
    expect(inline[0]!.attrs.src).toBe("/a")
    expect(inline[1]!.type).toBe("text")
    expect(inline[1]!.text).toBe("b.txt")
    expect(inline[1]!.href).toBe("/b")
    expect(inline[2]!.type).toBe("text")
    expect(inline[2]!.text).toBe(" ")
    expect(inline[2]!.href).toBe(null)
    expect(inline[3]!.type).toBe("text")
    expect(inline[3]!.text).toBe("c.txt")
    expect(inline[3]!.href).toBe("/c")
    expect(inline[4]!.type).toBe("text")
    expect(inline[4]!.text).toBe(" ")
    expect(inline[4]!.href).toBe(null)

    // All placeholders cleared.
    expect(decorationCount(editor.view, editor.plugin)).toBe(0)

    // No error toast on the success path.
    expect(mockShowFlash).not.toHaveBeenCalled()
  })

  test("upload tolerates partial success: server returns fewer attachments than files", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ attachments: [{ download_url: "/a" }, { download_url: "/b" }] }),
    } as unknown as Response)

    const a = makeImageFile("a.png")
    const b = makeImageFile("b.png")
    const c = makeImageFile("c.png")

    getUpload(editor.plugin)(editor.view, [a, b, c])
    await flushMicrotasks()

    // Only the first two were inserted; nothing left over for the missing third.
    const inline = inlineChildren(editor.view)
    expect(inline).toHaveLength(2)
    expect(inline[0]!.attrs.src).toBe("/a")
    expect(inline[1]!.attrs.src).toBe("/b")

    // The cleanup loop removes the orphan placeholder for the absent third file
    // after replacing the first two, so no placeholders remain.
    expect(decorationCount(editor.view, editor.plugin)).toBe(0)

    // Partial success is not a failure — no error toast.
    expect(mockShowFlash).not.toHaveBeenCalled()
  })

  test("upload failure removes all placeholders and inserts nothing", async () => {
    // The plugin logs the rejected upload via console.error; expected here.
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.resolve({}),
    } as unknown as Response)

    const a = makeImageFile("a.png")
    const b = makeImageFile("b.png")

    const beforeJSON = JSON.stringify(editor.view.state.doc.toJSON())
    getUpload(editor.plugin)(editor.view, [a, b])
    await flushMicrotasks()

    // Document is unchanged — no images or links inserted.
    expect(JSON.stringify(editor.view.state.doc.toJSON())).toBe(beforeJSON)
    // All placeholders cleaned up.
    expect(decorationCount(editor.view, editor.plugin)).toBe(0)
    // A non-413 failure surfaces the generic retry toast.
    expect(mockShowFlash).toHaveBeenCalledTimes(1)
    expect(mockShowFlash).toHaveBeenCalledWith("That file couldn't be uploaded. Please try again.", "error")
    consoleError.mockRestore()
  })

  test("413 rejection shows the server's size-limit toast and removes placeholders", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 413,
      json: () => Promise.resolve({ detail: "Files must be 25 MB or smaller." }),
    } as unknown as Response)

    const a = makeImageFile("a.png")

    const beforeJSON = JSON.stringify(editor.view.state.doc.toJSON())
    getUpload(editor.plugin)(editor.view, [a])
    await flushMicrotasks()

    // Document is unchanged and placeholders are cleaned up.
    expect(JSON.stringify(editor.view.state.doc.toJSON())).toBe(beforeJSON)
    expect(decorationCount(editor.view, editor.plugin)).toBe(0)
    // A 413 is about the file itself — surface the server's size-limit message verbatim.
    expect(mockShowFlash).toHaveBeenCalledTimes(1)
    expect(mockShowFlash).toHaveBeenCalledWith("Files must be 25 MB or smaller.", "error")
    consoleError.mockRestore()
  })

  test("handleDrop and handlePaste both batch all files into a single fetch", async () => {
    // Hold the request open so we can deterministically assert the call count
    // without races against promise resolution scheduling.
    mockFetch.mockReturnValue(new Promise(() => {}))

    // Build a DragEvent with three file items via dataTransfer.items.getAsFile().
    const dropFiles = [makeImageFile("d1.png"), makeImageFile("d2.png"), makeTextFile("d3.txt")]
    const dropItems = dropFiles.map(file => ({
      kind: "file" as const,
      getAsFile: () => file,
    }))
    const stopPropagation = vi.fn()
    const dragEvent = {
      dataTransfer: { items: dropItems },
      stopPropagation,
    } as unknown as DragEvent

    const dropHandled = editor.plugin.props.handleDrop?.(editor.view, dragEvent, undefined as never, true)
    expect(dropHandled).toBe(true)
    // A handled in-editor drop stops propagation so the composer's box-scoped
    // dropzone doesn't re-upload the same file appended at the end.
    expect(stopPropagation).toHaveBeenCalledTimes(1)

    expect(mockFetch).toHaveBeenCalledTimes(1)
    {
      const { files } = inspectFormData(mockFetch.mock.calls[0]![1]!.body as FormData)
      expect(files.map(f => f.name)).toEqual(["d1.png", "d2.png", "d3.txt"])
    }

    // Now exercise the paste path with a separate set of three files.
    mockFetch.mockClear()
    mockFetch.mockReturnValue(new Promise(() => {}))
    const pasteFiles = [makeImageFile("p1.png"), makeImageFile("p2.png"), makeTextFile("p3.txt")]
    const pasteItems = pasteFiles.map(file => ({
      kind: "file" as const,
      getAsFile: () => file,
    }))
    const pasteEvent = {
      clipboardData: { items: pasteItems },
    } as unknown as ClipboardEvent

    const pasteHandled = editor.plugin.props.handlePaste?.(editor.view, pasteEvent, undefined as never)
    expect(pasteHandled).toBe(true)

    expect(mockFetch).toHaveBeenCalledTimes(1)
    {
      const { files } = inspectFormData(mockFetch.mock.calls[0]![1]!.body as FormData)
      expect(files.map(f => f.name)).toEqual(["p1.png", "p2.png", "p3.txt"])
    }
  })
})

// A compact block-by-block view of the doc: each top-level block as `type[child,child]`,
// where inline images render as `image` and text as its quoted content. Lets us assert that
// an uploaded image lands in its own paragraph rather than sharing a block with text.
function blockShape(view: EditorView): string {
  const parts: string[] = []
  view.state.doc.forEach(block => {
    const inner: string[] = []
    block.forEach(child => inner.push(child.isText ? JSON.stringify(child.text) : child.type.name))
    parts.push(`${block.type.name}[${inner.join(",")}]`)
  })
  return parts.join(" ")
}

describe("attachments plugin — uploaded images occupy their own paragraph", () => {
  // #8840: `image` is an inline node, so inserting it inline left the caret in the image's
  // paragraph; the next keystrokes produced `paragraph[image, text]`, which broke heading
  // conversion (it dropped the image). An upload batch must sit in its own paragraph, isolated from
  // surrounding text, with the caret past it.
  beforeEach(() => {
    mockFetch.mockReset()
    mockShowFlash.mockReset()
  })

  function editorWith(doc: import("prosemirror-model").Node) {
    const container = document.createElement("div")
    document.body.appendChild(container)
    const plugin = getAttachmentsPlugin("/upload", "claim-1")
    const state = EditorState.create({ doc, schema, plugins: [plugin] })
    const view = new EditorView(container, { state })
    const upload = (plugin.spec as unknown as { upload: (v: EditorView, f: File[]) => void }).upload
    return { view, container, upload }
  }

  function resolveOnce(url: string) {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ attachments: [{ download_url: url }] }),
    } as unknown as Response)
  }

  test("image dropped into an empty line gets its own paragraph with the caret in a fresh block below", async () => {
    const { view, container, upload } = editorWith(schema.node("doc", null, [schema.node("paragraph")]))
    resolveOnce("/a")
    upload(view, [makeImageFile("a.png")])
    await new Promise(resolve => setTimeout(resolve, 0))

    // A fresh block follows the image so typing starts a new paragraph rather than joining the
    // image's (which would break gallery grouping). The unused trailing block is stripped at send
    // time — see the useEnterToSend tests.
    expect(blockShape(view)).toBe("paragraph[image] paragraph[]")
    const { $from } = view.state.selection
    expect($from.parent.type.name).toBe("paragraph")
    expect($from.parent.content.size).toBe(0)
    expect($from.index(-1)).toBe(1)

    view.destroy()
    container.remove()
  })

  test("image inserted mid-text splits the paragraph and never shares a block with text", async () => {
    const doc = schema.node("doc", null, [schema.node("paragraph", null, [schema.text("Hello")])])
    const { view, container, upload } = editorWith(doc)
    // Place the caret in the middle: "Hel|lo".
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 4)))
    resolveOnce("/a")
    upload(view, [makeImageFile("a.png")])
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(blockShape(view)).toBe('paragraph["Hel"] paragraph[image] paragraph["lo"]')

    view.destroy()
    container.remove()
  })

  test("a batch of images shares one paragraph so the chat gallery still groups them", async () => {
    // Chat groups consecutive images that share a paragraph into a gallery (extractImageGroup in
    // react/composites/markdown/Markdown.tsx). One-paragraph-per-image would serialize to separate
    // markdown paragraphs and defeat that grouping, so a whole upload batch stays in one paragraph.
    const { view, container, upload } = editorWith(schema.node("doc", null, [schema.node("paragraph")]))
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({ attachments: [{ download_url: "/a" }, { download_url: "/b" }, { download_url: "/c" }] }),
    } as unknown as Response)
    upload(view, [makeImageFile("a.png"), makeImageFile("b.png"), makeImageFile("c.png")])
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(blockShape(view)).toBe("paragraph[image,image,image] paragraph[]")
    // All three images serialize into a single markdown paragraph (no blank lines between them),
    // which is what the gallery grouping keys off of. (The trailing empty block is the caret target;
    // it's stripped at send — see the useEnterToSend tests.)
    expect(serialize(view.state.doc)).toBe("![](/a)![](/b)![](/c)\n\n<br />\n")

    view.destroy()
    container.remove()
  })

  test("a batch dropped mid-text splits once, keeping the whole batch in one paragraph", async () => {
    const doc = schema.node("doc", null, [schema.node("paragraph", null, [schema.text("Hello")])])
    const { view, container, upload } = editorWith(doc)
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 4))) // Hel|lo
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ attachments: [{ download_url: "/a" }, { download_url: "/b" }] }),
    } as unknown as Response)
    upload(view, [makeImageFile("a.png"), makeImageFile("b.png")])
    await new Promise(resolve => setTimeout(resolve, 0))

    // One split around a single shared batch paragraph — no empty paragraphs wedged between images,
    // and the trailing text becomes the caret's block.
    expect(blockShape(view)).toBe('paragraph["Hel"] paragraph[image,image] paragraph["lo"]')
    const { $from } = view.state.selection
    expect($from.parent.textContent).toBe("lo")
    expect($from.parentOffset).toBe(0)

    view.destroy()
    container.remove()
  })

  test("a mixed batch of images and file links shares one paragraph, in order", async () => {
    const { view, container, upload } = editorWith(schema.node("doc", null, [schema.node("paragraph")]))
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({ attachments: [{ download_url: "/a" }, { download_url: "/doc" }, { download_url: "/b" }] }),
    } as unknown as Response)
    upload(view, [makeImageFile("a.png"), makeTextFile("notes.txt"), makeImageFile("b.png")])
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(blockShape(view)).toBe('paragraph[image,"notes.txt"," ",image] paragraph[]')

    view.destroy()
    container.remove()
  })
})
