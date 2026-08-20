import { useStore } from "zustand"

import { Dialog } from "~/react/ui/Dialog"
import { confirmationDialogStore } from "./store"

const TITLE_ID = "confirmation-dialog-title"
const MESSAGE_ID = "confirmation-dialog-message"

export function ConfirmationDialog() {
  const current = useStore(confirmationDialogStore, s => s.current)
  const resolve = useStore(confirmationDialogStore, s => s.resolve)
  const reject = useStore(confirmationDialogStore, s => s.reject)

  if (!current) return null

  const confirmLabel = current.confirmLabel ?? "Confirm"
  const cancelLabel = current.cancelLabel ?? "Cancel"
  const labelledBy = current.title ? TITLE_ID : MESSAGE_ID

  return (
    <Dialog
      isOpen
      onClose={reject}
      labelledBy={labelledBy}
      testId="confirmation-dialog"
      className="floating-card w-11/12 max-w-sm"
      // A global meta-dialog invoked from within other modals (including
      // body-portaled ones like the research dialog), so its overlay must sit
      // above the z-50 modal band and the bottom-sheet/shield bands regardless
      // of DOM order.
      overlayZIndexClassName="z-[90]"
      // Focus the Cancel button (first tabbable) by default so pressing Enter
      // doesn't accidentally confirm destructive actions — matches macOS/iOS
      // native dialog convention.
      initialFocus={0}
    >
      <div className="flex flex-col gap-4">
        {current.title && (
          <h3 id={TITLE_ID} className="font-semibold">
            {current.title}
          </h3>
        )}
        <p id={MESSAGE_ID} className="text-sm">
          {current.message}
        </p>
        <div className="flex items-center justify-end gap-2">
          <button type="button" className="btn" onClick={reject} data-testid="confirmation-dialog-cancel">
            {cancelLabel}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={resolve}
            data-testid="confirmation-dialog-confirm"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </Dialog>
  )
}
