import { useEffect, useRef, useState } from "react"

import { EditorFeatureOverlays } from "~/react/composites/editor/components/EditorFeatureOverlays"
import { Editor, EditorContent } from "~/react/composites/editor/Editor"
import { uploadFilesToView } from "~/react/composites/editor/features/useAttachments"
import { useCommonFeatures } from "~/react/composites/editor/features/useCommonFeatures"
import { useViewPlugin } from "~/react/composites/editor/features/useViewPlugin"
import { useViewRef } from "~/react/composites/editor/features/useViewRef"
import { BaseStatusDropdown } from "~/react/composites/StatusDropdown"
import type { GoalUpdateSubmitData } from "~/react/features/goalShow/types"
import { attachmentUploadUrl } from "~/react/shared/attachmentUrls"
import { useDropzone } from "~/react/shared/hooks/useDropzone"
import type { Goal } from "~/react/shared/types"
import { DropzoneOverlay } from "~/react/ui/DropzoneOverlay"
import { SubmitButton } from "~/react/ui/SubmitButton"

import { ProgressRingSlider } from "./ProgressRingSlider"

interface UpdateFormProps {
  goal: Goal
  questionText: string
  initialAnswer?: string
  onSubmit: (data: GoalUpdateSubmitData) => Promise<unknown>
  onComplete: (data: Omit<GoalUpdateSubmitData, "is_draft">) => Promise<unknown>
  onCancel: () => void
  submitting: boolean
  onDraftChange?: (data: GoalUpdateSubmitData) => void
  onDirtyChange?: (dirty: boolean) => void
  badgeText?: string
  noCard?: boolean
}

export function UpdateForm({
  goal,
  questionText,
  initialAnswer,
  onSubmit,
  onComplete,
  onCancel,
  submitting,
  onDraftChange,
  onDirtyChange,
  badgeText = "New Update",
  noCard,
}: UpdateFormProps) {
  const [answerText, setAnswerText] = useState(initialAnswer ?? "")
  const [status, setStatus] = useState(goal.status)
  const [isCompleted, setIsCompleted] = useState(goal.is_completed)
  const [progress, setProgress] = useState<number | null>(goal.progress)

  const statusRef = useRef(status)
  useEffect(() => {
    statusRef.current = status
  }, [status])
  const progressRef = useRef(progress)
  useEffect(() => {
    progressRef.current = progress
  }, [progress])

  const commonFeatures = useCommonFeatures({ uploadUrl: attachmentUploadUrl(goal.workspace_id) })
  const attachments = commonFeatures.attachments

  // Lets the composer know when there's an in-progress update so it won't
  // collapse (and unmount this form, discarding the draft) on an outside click.
  // Uploads count as dirty too: a file dropped before any text is typed is only
  // a decoration until it finishes, so answerText alone would miss the in-flight upload.
  useEffect(() => {
    onDirtyChange?.(answerText.trim().length > 0 || attachments.hasUploads)
  }, [answerText, attachments.hasUploads, onDirtyChange])

  const { viewRef, plugin: viewRefPlugin } = useViewRef()

  // A drop anywhere on the composer uploads into the editor. In-editor drops are
  // inserted at the caret by the attachments plugin (which stops them bubbling
  // here), so this only catches drops outside the editable.
  const { isDragOver, ref: dropzoneRef } = useDropzone({
    onFiles: files => uploadFilesToView(viewRef.current, attachments, files),
  })

  const viewPlugin = useViewPlugin({
    onChange: md => {
      setAnswerText(md)
      if (onDraftChange && md.trim()) {
        onDraftChange({
          status: statusRef.current,
          question_text: questionText,
          answer_text: md.trim(),
          progress: progressRef.current,
        })
      }
    },
  })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (submitting || !answerText.trim()) return

    const data = {
      status,
      question_text: questionText,
      answer_text: answerText.trim(),
      progress,
    }

    if (isCompleted) {
      await onComplete(data)
    } else {
      await onSubmit(data)
    }
  }

  function handleStatusChange(value: string) {
    if (value === "complete") {
      setIsCompleted(true)
    } else {
      setIsCompleted(false)
      setStatus(value)
    }
  }

  const formContent = (
    <form ref={dropzoneRef} onSubmit={handleSubmit} className="relative">
      {isDragOver && <DropzoneOverlay />}
      <div className="p-4">
        <Editor
          features={[...commonFeatures.features, viewPlugin, { plugins: [viewRefPlugin] }]}
          placeholder={questionText}
          className="w-full min-h-16 max-h-96 overflow-y-auto focus:outline-hidden rounded-none px-0 py-2 bg-transparent text-sm"
          autoFocus
          showDropCursor={false}
        >
          <EditorContent />
          <EditorFeatureOverlays bundle={commonFeatures} />
        </Editor>
      </div>
      {/* Status, progress, and actions share one row to keep the composer compact. */}
      <div className="px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-3 border-t border-base-300">
        <div className="flex items-center shrink-0">
          <BaseStatusDropdown status={status} isCompleted={isCompleted} onSelect={handleStatusChange} />
        </div>
        <ProgressRingSlider value={progress} onChange={setProgress} />
        <div className="flex items-center gap-2 ml-auto">
          <button type="button" onClick={onCancel} className="btn btn-ghost btn-sm">
            Cancel
          </button>
          <SubmitButton submitting={submitting} className="btn btn-primary btn-sm">
            Submit update
          </SubmitButton>
        </div>
      </div>
    </form>
  )

  if (noCard) return formContent

  return (
    <div className="bg-base-50 rounded-xl border border-base-300 shadow-xs relative">
      <div className="absolute left-3 -top-3 dropdown-card rounded-lg inline-flex items-center px-2 py-1 shadow-sm">
        <span className="text-xs text-base-600/70 font-semibold">{badgeText}</span>
      </div>
      {formContent}
    </div>
  )
}
