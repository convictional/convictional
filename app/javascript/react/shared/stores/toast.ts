import { createStore } from "zustand/vanilla"

export type ToastLevel = "error" | "success"

export interface Toast {
  id: number
  message: string
  level: ToastLevel
  url?: string
  persistent: boolean
}

interface ToastState {
  toasts: Toast[]
  show: (toast: Omit<Toast, "id">) => number
  dismiss: (id: number) => void
}

let nextId = 0

// Module-level singleton so non-React modules — `shared/flash.ts` (and through
// it `shared/csrf.ts`) — can call `toastStore.getState().show(...)` without
// sharing a React tree with the <Toaster>. Mirrors feedbackDialog.ts.
export const toastStore = createStore<ToastState>(set => ({
  toasts: [],
  show: toast => {
    const id = nextId++
    set(state => ({ toasts: [...state.toasts, { ...toast, id }] }))
    return id
  },
  dismiss: id => set(state => ({ toasts: state.toasts.filter(t => t.id !== id) })),
}))

export type { ToastState }
