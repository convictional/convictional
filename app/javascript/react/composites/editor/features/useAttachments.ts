import { EditorView } from "prosemirror-view"
import { useCallback, useMemo, useState } from "react"

import getAttachmentsPlugin from "~/richText/plugins/attachments"
import type { EditorFeature } from "../types"

interface UseAttachmentsOptions {
  uploadUrl: string | null
  claimId?: string
  // Defer in-editor drop handling to a parent dropzone (e.g. chat surfaces).
  // Paste handling is unaffected.
  handleDrops?: boolean
}

export interface AttachmentsFeature extends EditorFeature {
  claimId: string
  upload: (view: EditorView, files: File[]) => void
  // True while any upload is in flight. Lets a consumer keep its form mounted
  // during that window, when the doc is still empty (see onUpload). Falls back
  // to false once uploads settle, including when they fail.
  hasUploads: boolean
}

export function useAttachments({
  uploadUrl,
  claimId: externalClaimId,
  handleDrops = true,
}: UseAttachmentsOptions): AttachmentsFeature {
  const internalClaimId = useMemo(() => crypto.randomUUID(), [])
  const claimId = externalClaimId ?? internalClaimId
  // Count in-flight uploads rather than a one-way flag: a failed upload removes its
  // placeholder and leaves the doc empty again, so hasUploads has to fall back to false.
  const [uploadsInFlight, setUploadsInFlight] = useState(0)
  const hasUploads = uploadsInFlight > 0
  const markUploadStarted = useCallback(() => setUploadsInFlight(count => count + 1), [])
  const markUploadSettled = useCallback(() => setUploadsInFlight(count => Math.max(0, count - 1)), [])
  const plugin = useMemo(
    () =>
      uploadUrl
        ? getAttachmentsPlugin(uploadUrl, claimId, {
            handleDrops,
            onUpload: markUploadStarted,
            onUploadSettled: markUploadSettled,
          })
        : null,
    [uploadUrl, claimId, handleDrops, markUploadStarted, markUploadSettled]
  )

  const upload = useCallback(
    (view: EditorView, files: File[]) => {
      if (plugin) {
        const fn = (plugin.spec as { upload: (v: EditorView, f: File[]) => void }).upload
        fn(view, files)
      }
    },
    [plugin]
  )

  // Memoized so consumers that depend on the whole feature object (the editor
  // imperative handles) keep a stable identity across renders.
  return useMemo(
    () => ({ plugins: plugin ? [plugin] : [], claimId, upload, hasUploads }),
    [plugin, claimId, upload, hasUploads]
  )
}

// Pushes dropped/selected files into the editor: focus the view first so the
// upload lands at the caret, then hand off to the attachments feature.
export function uploadFilesToView(view: EditorView | null, attachments: AttachmentsFeature, files: File[]) {
  if (!view) return
  view.focus()
  attachments.upload(view, files)
}

// Opens the native file picker and uploads the chosen files through the
// attachments feature. Shared by the toolbar attach button and the chat handle
// so the transient-input + Safari workaround live in one place.
export function openFilePickerAndUpload(view: EditorView | null, attachments: AttachmentsFeature) {
  if (!view) return
  const input = document.createElement("input")
  input.type = "file"
  input.multiple = true
  input.style.display = "none"
  // Safari drops the change event if the input is removed before the file
  // picker resolves, so clean up only after change/cancel fires.
  const cleanup = () => input.remove()
  input.onchange = () => {
    if (input.files?.length) {
      // Focus before insert so the upload lands at a live caret, and to
      // stay consistent with the drop path (uploadFilesToView focuses too).
      view.focus()
      attachments.upload(view, Array.from(input.files))
    }
    cleanup()
  }
  input.oncancel = cleanup
  document.body.appendChild(input)
  input.click()
}
