import { Dialog } from "~/react/ui/Dialog"

interface DraftConflictDialogProps {
  open: boolean
  replyType: string
  onConfirm: () => void
  onCancel: () => void
}

// 409 conflict modal: shown after a Reply/Reply All/Forward attempt finds an
// existing draft on the thread. Confirming reposts with `replace_existing=true`;
// the parent owns that fetch.
export function DraftConflictDialog({ open, replyType, onConfirm, onCancel }: DraftConflictDialogProps) {
  if (!open) return null
  return (
    <Dialog isOpen={open} onClose={onCancel} className="bg-base-100 rounded-lg max-w-md w-full p-4 shadow-xl">
      <h2 className="text-base font-semibold mb-2">Replace existing draft?</h2>
      <p className="text-sm mb-4">
        There is already a draft on this thread. Continuing with this {replyType.replace("_", " ") || "reply"} will
        replace it.
      </p>
      <div className="flex justify-end gap-2">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary btn-sm" onClick={onConfirm}>
          Replace draft
        </button>
      </div>
    </Dialog>
  )
}
