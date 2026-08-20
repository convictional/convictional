import { createStore } from "zustand/vanilla"

export interface ConfirmationRequest {
  message: string
  title?: string
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel?: () => void
}

interface ConfirmationDialogState {
  current: ConfirmationRequest | null
  open: (request: ConfirmationRequest) => void
  resolve: () => void
  reject: () => void
}

// Module-level singleton so triggers in any island — or the htmx:confirm
// bridge — can call `confirmationDialogStore.getState().open(...)` without
// sharing a React tree with the dialog. Mirrors feedbackDialog.ts.
export const confirmationDialogStore = createStore<ConfirmationDialogState>((set, get) => ({
  current: null,
  open: request => {
    // If another confirmation is already open, treat the new one as taking
    // over: cancel the previous so its caller's onCancel/Promise resolves.
    const existing = get().current
    if (existing) existing.onCancel?.()
    set({ current: request })
  },
  resolve: () => {
    const current = get().current
    if (!current) return
    set({ current: null })
    current.onConfirm()
  },
  reject: () => {
    const current = get().current
    if (!current) return
    set({ current: null })
    current.onCancel?.()
  },
}))
