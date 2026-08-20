import { confirmationDialogStore } from "./store"

export interface ConfirmOptions {
  message: string
  title?: string
  confirmLabel?: string
  cancelLabel?: string
}

// Promise-based drop-in for window.confirm. Resolves true if the user confirms,
// false if they cancel (by clicking Cancel, pressing Esc, or clicking outside).
export function confirm(options: ConfirmOptions): Promise<boolean> {
  return new Promise(resolve => {
    confirmationDialogStore.getState().open({
      ...options,
      onConfirm: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })
}
