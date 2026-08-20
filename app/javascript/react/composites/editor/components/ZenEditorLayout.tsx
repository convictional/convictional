import type { EditorView } from "prosemirror-view"
import type { ReactNode, RefObject } from "react"

import { SyncStatus } from "~/react/composites/SyncStatus"
import { TitleInput } from "~/react/composites/TitleInput"
import { useDropzone } from "~/react/shared/hooks/useDropzone"
import { DropzoneOverlay } from "~/react/ui/DropzoneOverlay"

import { Editor, EditorContent } from "../Editor"
import { type AttachmentsFeature, uploadFilesToView } from "../features/useAttachments"
import { useZenMode } from "../features/useZenMode"
import type { EditorFeature, SyncStatus as SyncStatusType } from "../types"
import { Toolbar } from "./Toolbar"

interface ZenEditorLayoutProps {
  containerRef: RefObject<HTMLDivElement | null>
  features: EditorFeature[]
  docSynced: boolean
  toolbar: {
    hasKlipy: boolean
    klipyApiKey: string | null
    enableTableInsert?: boolean
    portalId: string
    grouped?: boolean
  }
  syncStatus: {
    status: SyncStatusType
    docSynced: boolean
    portalId: string
  }
  title: {
    saveUrl: string
    initialTitle: string
    placeholder: string
    autoSelectTitle: string
  }
  // Attachments feature + live view ref, threaded so the toolbar attach button
  // and the drag-and-drop overlay can upload. Omit both to disable the affordance.
  attachments?: AttachmentsFeature
  viewRef?: RefObject<EditorView | null>
  children?: ReactNode
}

export function ZenEditorLayout({
  containerRef,
  features,
  docSynced,
  toolbar,
  syncStatus,
  title,
  attachments,
  viewRef,
  children,
}: ZenEditorLayoutProps) {
  const { zenMode, exiting, toggleZenMode } = useZenMode()
  const dropzoneEnabled = !!(attachments && viewRef)
  const { isDragOver, ref: dropzoneRef } = useDropzone({
    onFiles: files => {
      if (attachments && viewRef) uploadFilesToView(viewRef.current, attachments, files)
    },
    enabled: dropzoneEnabled,
  })

  return (
    <div className={zenMode ? `zen-mode ${exiting ? "zen-exit" : "zen-enter"}` : ""}>
      <Editor
        features={features}
        placeholder="Start writing..."
        className="w-full focus:outline-hidden rounded-none px-0 py-2 bg-transparent min-h-[50vh]"
        showDropCursor={!dropzoneEnabled}
      >
        <div ref={containerRef} className={`relative ${zenMode ? "zen-scroll" : ""}`}>
          {!docSynced && <style>{`.ProseMirror[data-placeholder]::before { display: none !important; }`}</style>}
          {zenMode && (
            <button
              type="button"
              className="zen-close btn btn-ghost btn-square btn-sm"
              onClick={toggleZenMode}
              title="Exit zen mode (Esc)"
            >
              <span className="material-symbols-outlined !text-lg">close</span>
            </button>
          )}
          {!zenMode && (
            <>
              <SyncStatus
                status={syncStatus.status}
                docSynced={syncStatus.docSynced}
                portalTarget={document.getElementById(syncStatus.portalId)}
              />
              <Toolbar
                hasKlipy={toolbar.hasKlipy}
                klipyApiKey={toolbar.klipyApiKey}
                enableTableInsert={toolbar.enableTableInsert}
                portalTarget={document.getElementById(toolbar.portalId)}
                onToggleZen={toggleZenMode}
                grouped={toolbar.grouped}
                attachments={attachments}
              />
            </>
          )}
          <div className={zenMode ? "zen-content" : ""}>
            <TitleInput
              saveUrl={title.saveUrl}
              initialTitle={title.initialTitle}
              placeholder={title.placeholder}
              autoSelectTitle={title.autoSelectTitle}
            />
            <div ref={dropzoneRef} className="relative">
              {isDragOver && <DropzoneOverlay />}
              <EditorContent />
            </div>
          </div>
          {children}
        </div>
      </Editor>
    </div>
  )
}
