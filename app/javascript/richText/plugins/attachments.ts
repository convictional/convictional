import { Fragment, Node } from "prosemirror-model"
import { Plugin, Transaction, EditorState, TextSelection } from "prosemirror-state"
import { Decoration, DecorationSet, EditorView } from "prosemirror-view"

import { fetchWithCSRF } from "~/shared/csrf"
import { showFlash } from "~/shared/flash"
import { schema } from "../schema"

interface AttachmentMeta {
  add?: {
    id: object
    pos: number
  }
  remove?: {
    id: object
  }
}

interface DecorationSpec {
  id: object
}

interface AttachmentsPluginOptions {
  // Editors that live inside a wrapper owning drop handling (the chat surface,
  // or a composer's box-scoped dropzone) opt out so the same drop isn't
  // uploaded twice.
  handleDrops?: boolean
  // Fires when an upload begins (before it completes). Lets a surrounding form
  // treat itself as dirty during the in-flight window, when the placeholder is
  // only a decoration and the doc is still empty.
  onUpload?: () => void
  // Fires when an upload finishes, whether it succeeded or failed. Paired with
  // onUpload so the form can drop the in-flight dirty state once nothing is
  // pending; on failure the placeholder is removed and the doc goes back to empty.
  onUploadSettled?: () => void
}

// `image` is an inline node (markdown images are inline in prosemirror-remark). Inserting it inline
// at the caret leaves the caret in the image's paragraph, so the user's next keystrokes join the
// image's block and produce `paragraph[image, text]`. That malformed structure is what later
// corrupts the doc — heading conversion over it drops the image (#8840). Isolate a whole upload
// batch in its own paragraph, with the caret in a fresh paragraph after it, so attachments and text
// can never share a block.
//
// The batch stays in a single paragraph (rather than one paragraph per attachment): chat renders
// consecutive images that share a paragraph as a gallery, so splitting them apart would break that
// grouping (see extractImageGroup in react/composites/markdown/Markdown.tsx).
function insertAttachmentsInOwnParagraph(state: EditorState, pos: number, inlineNodes: Node[]): Transaction {
  const fragment = Fragment.from(inlineNodes)
  const attachmentParagraph = schema.nodes.paragraph.create(null, fragment)
  const $pos = state.doc.resolve(pos)
  const container = $pos.node(-1)
  const indexInContainer = $pos.index(-1)

  // Defensive, mirroring the toggleHeading fix: some containers (e.g. a table_cell whose content
  // spec is a single `paragraph`) can't hold an extra paragraph block. Rather than lift, pad, or
  // corrupt the doc, fall back to an inline insert at the caret.
  if (!container.canReplaceWith(indexInContainer, indexInContainer, schema.nodes.paragraph)) {
    return state.tr.replaceWith(pos, pos, fragment)
  }

  const tr = state.tr
  let insidePos: number
  if ($pos.parent.isTextblock && $pos.parent.content.size === 0) {
    // Drag/paste into an empty line: drop the batch straight into the blank block so it becomes
    // `paragraph[...attachments]`. Inserting inline (rather than replacing the block) keeps the
    // block's attrs. The mapped caret position stays inside the now-filled block.
    tr.replaceWith(pos, pos, fragment)
    insidePos = tr.mapping.map(pos)
  } else {
    // Caret within/among text: insert the batch in its own block, which splits the surrounding
    // textblock around it so the attachments never share a paragraph with text.
    tr.replaceWith(pos, pos, attachmentParagraph)
    // Locate the just-inserted paragraph by identity to find where it ends. Scanning (rather than
    // mapping arithmetic) stays correct across the textblock split above and at any container depth.
    let paragraphPos = -1
    tr.doc.nodesBetween($pos.before(), tr.doc.content.size, (node, position) => {
      if (paragraphPos !== -1) return false
      if (node.type === schema.nodes.paragraph && node.eq(attachmentParagraph)) paragraphPos = position
      return paragraphPos === -1
    })
    insidePos = paragraphPos + 1
  }
  const endOfAttachmentParagraph = tr.doc.resolve(insidePos).after()

  // Land the caret in a fresh block after the batch, not back inside it: text typed into the
  // attachments' paragraph would give it a non-image sibling and break the chat gallery grouping.
  // When text already follows (the tail of a mid-text split) that block is the target; otherwise
  // synthesize an empty paragraph. A trailing empty paragraph left unused is stripped when the doc
  // is serialized for send/save (see withoutTrailingEmptyBlocks in richText/schema), so it doesn't
  // become a blank line.
  const $end = tr.doc.resolve(endOfAttachmentParagraph)
  if ($end.nodeAfter && $end.nodeAfter.isTextblock) {
    tr.setSelection(TextSelection.near(tr.doc.resolve(endOfAttachmentParagraph), 1))
  } else {
    tr.insert(endOfAttachmentParagraph, schema.nodes.paragraph.create())
    tr.setSelection(TextSelection.near(tr.doc.resolve(endOfAttachmentParagraph + 1), 1))
  }
  return tr
}

function getAttachmentsPlugin(uploadURL: string, claimID: string, options: AttachmentsPluginOptions = {}): Plugin {
  const { handleDrops = true, onUpload, onUploadSettled } = options
  const plugin: Plugin = new Plugin<DecorationSet>({
    state: {
      init() {
        return DecorationSet.empty
      },
      apply(tr: Transaction, set: DecorationSet) {
        set = set.map(tr.mapping, tr.doc)

        const action = tr.getMeta(plugin) as AttachmentMeta | undefined

        if (action?.add) {
          const widget = document.createTextNode("Uploading...")
          const deco = Decoration.widget(action.add.pos, widget, {
            id: action.add.id,
          } as DecorationSpec)
          set = set.add(tr.doc, [deco])
        } else if (action?.remove) {
          set = set.remove(set.find(undefined, undefined, (spec: DecorationSpec) => spec.id === action.remove?.id))
        }
        return set
      },
    },
    props: {
      decorations(state: EditorState) {
        return plugin.getState(state)
      },
      handleDrop(view: EditorView, event: DragEvent) {
        if (!handleDrops) return false
        if (!event.dataTransfer) return false
        const items = Array.from(event.dataTransfer.items)
        const handled = handleDataTransfer(view, items)
        // A drop on the editable inserts at the caret the browser placed at the
        // drop point. Stop it bubbling to the composer's box-scoped dropzone,
        // which would otherwise re-upload the same file (appended at the end).
        if (handled) event.stopPropagation()
        return handled
      },
      handlePaste(view: EditorView, event: ClipboardEvent) {
        if (!event.clipboardData) return false
        const items = Array.from(event.clipboardData.items)
        return handleDataTransfer(view, items)
      },
    },
    upload,
  })

  function handleDataTransfer(view: EditorView, items: DataTransferItem[]): boolean {
    const files = items.filter(item => item.kind === "file")
    if (files.length === 0) return false

    const fileObjects: File[] = []
    files.forEach(file => {
      const fileObject = file.getAsFile()
      if (fileObject) {
        fileObjects.push(fileObject)
      }
    })

    if (fileObjects.length > 0) {
      upload(view, fileObjects)
    }

    return true
  }

  function findPlaceholder(state: EditorState, id: object): number | null {
    const decos = plugin.getState(state)
    const found = decos.find(null, null, (spec: DecorationSpec) => spec.id === id)
    return found.length ? found[0].from : null
  }

  function upload(view: EditorView, files: File[]): void {
    if (files.length === 0) return

    onUpload?.()

    const fileIds = files.map(file => ({ file, id: {} }))

    if (!view.state.selection.empty) {
      view.dispatch(view.state.tr.deleteSelection())
    }

    const startPos = view.state.selection.from
    fileIds.forEach(({ id }) => {
      const tr = view.state.tr
      tr.setMeta(plugin, { add: { id, pos: startPos } })
      view.dispatch(tr)
    })

    const formData = new FormData()
    files.forEach(file => {
      formData.append("files", file)
    })
    formData.append("claim_id", claimID)

    fetchWithCSRF(uploadURL, {
      method: "POST",
      body: formData,
    })
      .then(async (response: Response) => {
        if (!response.ok) {
          const error = new Error("Upload failed") as Error & { status?: number; detail?: string }
          error.status = response.status
          // The 413 handler sends a human-readable size limit in `detail`; carry it
          // through so the toast stays in sync with the server's limit.
          const body = await response.json().catch(() => null)
          if (body && typeof body.detail === "string") {
            error.detail = body.detail
          }
          throw error
        }
        return response.json()
      })
      .then((responseJSON: { attachments: Array<{ download_url: string }> }) => {
        // Build the ordered inline nodes for every attachment the server returned, then insert the
        // whole batch as one isolated paragraph (see insertAttachmentsInOwnParagraph): images stay
        // grouped for the chat gallery, and no attachment shares a block with the user's text.
        const inlineNodes: Node[] = []
        for (let index = 0; index < responseJSON.attachments.length; index++) {
          const { file } = fileIds[index]
          const url = responseJSON.attachments[index].download_url
          if (file.type.startsWith("image/")) {
            inlineNodes.push(schema.nodes.image.create({ src: url }))
          } else {
            // Trailing space separates adjacent links so consecutive uploads
            // don't render as "name1.pdfname2.pdf".
            inlineNodes.push(schema.text(file.name, [schema.marks.link.create({ href: url })]))
            inlineNodes.push(schema.text(" "))
          }
        }

        // Placeholders were all added at the same caret position, so any surviving one anchors the
        // batch (an intervening edit could have removed one).
        let pos: number | null = null
        for (const { id } of fileIds) {
          pos = findPlaceholder(view.state, id)
          if (pos !== null) break
        }

        if (pos !== null && inlineNodes.length > 0) {
          view.dispatch(insertAttachmentsInOwnParagraph(view.state, pos, inlineNodes))
        }

        // Clear every placeholder: those the batch replaced, plus any orphaned by files the server
        // didn't return (partial success).
        fileIds.forEach(({ id }) => {
          view.dispatch(view.state.tr.setMeta(plugin, { remove: { id } }))
        })
      })
      .catch((error: unknown) => {
        console.error("Attachment upload failed", error)
        // 413 is the only rejection about the file itself (too large), and the
        // server's detail carries the exact limit. Everything else (network, 5xx,
        // malformed request) gets the generic retry message.
        const uploadError = error instanceof Error ? (error as Error & { status?: number; detail?: string }) : null
        const message =
          uploadError?.status === 413
            ? (uploadError.detail ?? "That file is too large.")
            : "That file couldn't be uploaded. Please try again."
        showFlash(message, "error")
        fileIds.forEach(({ id }) => {
          view.dispatch(view.state.tr.setMeta(plugin, { remove: { id } }))
        })
      })
      .finally(() => {
        onUploadSettled?.()
      })
  }

  return plugin
}

export default getAttachmentsPlugin
