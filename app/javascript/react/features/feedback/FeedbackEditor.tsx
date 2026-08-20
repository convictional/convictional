import { forwardRef, useImperativeHandle } from "react"

import { EditorFeatureOverlays } from "~/react/composites/editor/components/EditorFeatureOverlays"
import { Toolbar } from "~/react/composites/editor/components/Toolbar"
import { Editor, EditorContent } from "~/react/composites/editor/Editor"
import { uploadFilesToView } from "~/react/composites/editor/features/useAttachments"
import { useCommonFeatures } from "~/react/composites/editor/features/useCommonFeatures"
import { useViewPlugin } from "~/react/composites/editor/features/useViewPlugin"
import { useViewRef } from "~/react/composites/editor/features/useViewRef"
import { useDropzone } from "~/react/shared/hooks/useDropzone"
import { DropzoneOverlay } from "~/react/ui/DropzoneOverlay"
import { schema, serialize } from "~/richText/schema"

export interface FeedbackEditorHandle {
  getContent: () => string
  isEmpty: () => boolean
  clear: () => void
  focus: () => void
  attachmentClaimId: string
}

interface FeedbackEditorProps {
  uploadUrl: string | null
  placeholder?: string
  autoFocus?: boolean
  onChange?: (markdown: string) => void
}

export const FeedbackEditor = forwardRef<FeedbackEditorHandle, FeedbackEditorProps>(function FeedbackEditor(
  { uploadUrl, placeholder = "Tell us what's working well or what we could improve...", autoFocus = true, onChange },
  ref
) {
  const { viewRef, plugin: viewRefPlugin } = useViewRef()
  const commonFeatures = useCommonFeatures({ mentionsEnabled: false, uploadUrl })
  const attachments = commonFeatures.attachments
  // ProseMirror suppresses the DOM `input` event; observe doc changes via
  // a view plugin's update() callback instead.
  const viewPlugin = useViewPlugin({ onChange: onChange ?? (() => {}) })
  const { isDragOver, ref: dropzoneRef } = useDropzone({
    onFiles: files => uploadFilesToView(viewRef.current, attachments, files),
    enabled: !!uploadUrl,
  })

  useImperativeHandle(
    ref,
    () => ({
      getContent: () => {
        const view = viewRef.current
        if (!view) return ""
        return serialize(view.state.doc)
      },
      isEmpty: () => {
        const view = viewRef.current
        if (!view) return true
        return view.state.doc.textContent.trim().length === 0
      },
      clear: () => {
        const view = viewRef.current
        if (!view) return
        const tr = view.state.tr.replaceWith(0, view.state.doc.content.size, schema.nodes.paragraph.create())
        view.dispatch(tr)
      },
      focus: () => viewRef.current?.focus(),
      attachmentClaimId: attachments.claimId,
    }),
    [viewRef, attachments.claimId]
  )

  return (
    <Editor
      features={[...commonFeatures.features, viewPlugin, { plugins: [viewRefPlugin] }]}
      placeholder={placeholder}
      className="markdown-content min-h-32 max-h-96 overflow-y-auto focus:outline-hidden text-sm p-3"
      autoFocus={autoFocus}
      showDropCursor={false}
    >
      <div ref={dropzoneRef} className="relative rounded-lg border border-neutral overflow-hidden bg-base-100">
        {isDragOver && <DropzoneOverlay />}
        <div className="border-b border-neutral px-2 py-1">
          <Toolbar hasKlipy={false} klipyApiKey={null} attachments={uploadUrl ? attachments : undefined} />
        </div>
        <EditorContent />
      </div>
      <EditorFeatureOverlays bundle={commonFeatures} />
    </Editor>
  )
})
