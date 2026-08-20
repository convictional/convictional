import { forwardRef, useImperativeHandle } from "react"

import { EditorFeatureOverlays } from "~/react/composites/editor/components/EditorFeatureOverlays"
import { Editor, EditorContent } from "~/react/composites/editor/Editor"
import { uploadFilesToView } from "~/react/composites/editor/features/useAttachments"
import { useCommonFeatures } from "~/react/composites/editor/features/useCommonFeatures"
import { DEBOUNCE_MS, useViewPlugin } from "~/react/composites/editor/features/useViewPlugin"
import { useViewRef } from "~/react/composites/editor/features/useViewRef"
import { parse, schema, serialize, withoutTrailingEmptyBlocks } from "~/richText/schema"

export interface RichTextComposerHandle {
  getContent: () => string
  isEmpty: () => boolean
  insertImage: (src: string, alt: string) => void
  uploadFiles: (files: File[]) => void
  focus: () => void
  // Drops a pending debounced onChange flush. Call before a remount-driven
  // clear so the unmount's destroy() flush can't resurrect stale content.
  cancelPendingChange: () => void
  attachmentClaimId: string
}

interface RichTextComposerProps {
  initialContent: string
  uploadUrl: string | null
  placeholder?: string
  className?: string
  autoFocus?: boolean
  onChange?: (markdown: string) => void
  // Off when a surrounding box dropzone shows its own "Drop to upload" overlay,
  // so the native drop-cursor line doesn't clash with it. The editor still
  // handles in-editor drops natively (insert at the drop point).
  showDropCursor?: boolean
}

// Stable identity so useViewPlugin's ref-sync effect doesn't re-run every
// render for consumers that pass no onChange.
const noop = () => {}

// The document-style rich-text composer: a multi-paragraph editor with no
// Enter-to-send (Enter inserts a newline; the surrounding form saves via its
// button) — the non-chat sibling of ChatComposerEditor. Shared by the post-body
// editor and the new-post composer.
export const RichTextComposer = forwardRef<RichTextComposerHandle, RichTextComposerProps>(function RichTextComposer(
  { initialContent, uploadUrl, placeholder, className, autoFocus = true, onChange, showDropCursor = true },
  ref
) {
  const { viewRef, plugin: viewRefPlugin } = useViewRef()
  // Post-body mentions are org-wide (no collaborator split), matching the
  // previous /workspaces/collaborators/available behaviour. The claim id is
  // exposed on the handle so the surrounding form forwards it on save, letting
  // the server associate uploads with the post's workspace.
  const commonFeatures = useCommonFeatures({ uploadUrl })
  // The hook always runs (rules of hooks) but the plugin is only installed
  // when a consumer observes changes — its update path serializes the whole
  // doc and dispatches scrollIntoView per edit, a cost no-onChange consumers
  // (the post body editor) shouldn't pay. Editor reads features once at
  // mount, and onChange presence is fixed per consumer, so the conditional
  // array is stable where it matters.
  const viewPlugin = useViewPlugin({ onChange: onChange ?? noop, debounceMs: DEBOUNCE_MS })
  const attachments = commonFeatures.attachments

  useImperativeHandle(
    ref,
    () => ({
      getContent: () => {
        const view = viewRef.current
        return view ? serialize(withoutTrailingEmptyBlocks(view.state.doc)) : ""
      },
      isEmpty: () => {
        const view = viewRef.current
        return view ? view.state.doc.textContent.trim().length === 0 : true
      },
      // GIF insert: drop an external image node at the selection. Mirrors the
      // chat composer's handle so the GifPicker can wire to either editor.
      insertImage: (src: string, alt: string) => {
        const view = viewRef.current
        if (!view || !src || !/^https?:\/\//i.test(src)) return
        const imageNode = schema.nodes.image.create({ src, alt })
        view.dispatch(view.state.tr.replaceSelectionWith(imageNode))
        view.focus()
      },
      // Lets a surrounding box-scoped dropzone push dropped files into the
      // editor (for drops outside the editable; in-editor drops are inserted
      // at the caret by the attachments plugin itself).
      uploadFiles: (files: File[]) => uploadFilesToView(viewRef.current, attachments, files),
      focus: () => viewRef.current?.focus(),
      cancelPendingChange: () => viewPlugin.cancel(),
      attachmentClaimId: attachments.claimId,
    }),
    [viewRef, viewPlugin, attachments]
  )

  return (
    <Editor
      features={[...commonFeatures.features, ...(onChange ? [viewPlugin] : []), { plugins: [viewRefPlugin] }]}
      doc={initialContent ? parse(initialContent) : (schema.nodes.doc.createAndFill() ?? undefined)}
      placeholder={placeholder}
      className={className ?? "min-h-40 max-h-96 overflow-y-auto w-full focus:outline-hidden px-0 py-2"}
      autoFocus={autoFocus}
      showDropCursor={showDropCursor}
    >
      <EditorContent />
      <EditorFeatureOverlays bundle={commonFeatures} />
    </Editor>
  )
})
