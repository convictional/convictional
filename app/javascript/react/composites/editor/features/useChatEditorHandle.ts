import { type RefObject, useImperativeHandle } from "react"

import { schema } from "~/richText/schema"
import { type AttachmentsFeature, openFilePickerAndUpload, uploadFilesToView } from "./useAttachments"
import type { EnterToSendFeature } from "./useEnterToSend"

export interface ChatEditorHandle {
  send: () => void
  focus: () => void
  triggerUpload: () => void
  uploadFiles: (files: File[]) => void
  insertImage: (src: string, alt: string) => void
  // Returns IDs of inline attachments currently referenced in the editor's
  // doc. Used on edit to tell the backend which previously-claimed attachments
  // to keep; everything else bound to the comment is treated as removed.
  getReferencedAttachmentIds: () => string[]
}

const ATTACHMENT_ID_PATTERN = /attachments\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i

export function useChatEditorHandle(
  ref: React.ForwardedRef<ChatEditorHandle>,
  enterToSend: EnterToSendFeature,
  viewRef: RefObject<import("prosemirror-view").EditorView | null>,
  attachments: AttachmentsFeature
) {
  useImperativeHandle(
    ref,
    () => ({
      send: () => enterToSend.send(),
      focus: () => viewRef.current?.focus(),
      triggerUpload: () => openFilePickerAndUpload(viewRef.current, attachments),
      uploadFiles: (files: File[]) => uploadFilesToView(viewRef.current, attachments, files),
      insertImage: (src: string, alt: string) => {
        const view = viewRef.current
        if (!view || !src || !/^https?:\/\//i.test(src)) return
        const imageNode = schema.nodes.image.create({ src, alt })
        const tr = view.state.tr.replaceSelectionWith(imageNode)
        view.dispatch(tr)
        view.focus()
      },
      getReferencedAttachmentIds: () => {
        const view = viewRef.current
        if (!view) return []
        const ids = new Set<string>()
        const collect = (value: string | undefined) => {
          const match = (value ?? "").match(ATTACHMENT_ID_PATTERN)
          if (match) ids.add(match[1].toLowerCase())
        }
        // Images embed the attachment URL in `src`; a non-image file rides a link mark's
        // href (attachments.ts inserts it as `[filename](download_url)`). Scan both so
        // edit retention keeps every referenced attachment, not just inline images.
        view.state.doc.descendants(node => {
          if (node.type === schema.nodes.image) {
            collect(node.attrs.src as string | undefined)
          }
          for (const mark of node.marks) {
            if (mark.type === schema.marks.link) {
              collect(mark.attrs.href as string | undefined)
            }
          }
        })
        return Array.from(ids)
      },
    }),
    [enterToSend, viewRef, attachments]
  )
}
