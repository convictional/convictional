import { useStore } from "zustand"

import { toastStore } from "~/react/shared/stores/toast"
import { ToastItem } from "./ToastItem"

export function Toaster() {
  const toasts = useStore(toastStore, s => s.toasts)

  if (toasts.length === 0) return null

  // Mirrors the Jinja `#flashes` container positioning in
  // application.html.jinja so React toasts sit where server flashes do:
  // top-14! clears the top nav; pt-[safe-area-inset-top] avoids the iOS notch.
  return (
    <div className="toast toast-center toast-top top-14! z-50 pt-[var(--safe-area-inset-top)]">
      {toasts.map(toast => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  )
}
