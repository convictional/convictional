import { confirmationDialogStore } from "./store"

interface HtmxConfirmDetail {
  elt: HTMLElement
  question: string | null
  issueRequest: (skipConfirmation: boolean) => void
}

// Intercepts htmx's pre-request `htmx:confirm` event so we can render the
// React ConfirmationDialog instead of the browser-native window.confirm.
// Calling event.preventDefault() + detail.issueRequest(true) is the htmx
// async-confirm pattern documented at https://htmx.org/events/#htmx:confirm.
//
// Per-element overrides on the htmx trigger (all optional):
//   data-confirm-label="Yes"         → custom confirm button text.
//   data-confirm-cancel-label="No"   → custom cancel button text.
//   data-confirm-title="Heads up"    → optional title above the message.
export function handleHtmxConfirm(event: Event): void {
  const detail = (event as CustomEvent<HtmxConfirmDetail>).detail
  const message = detail.question
  if (!message) return

  event.preventDefault()

  const elt = detail.elt
  confirmationDialogStore.getState().open({
    message,
    title: elt.dataset.confirmTitle,
    confirmLabel: elt.dataset.confirmLabel,
    cancelLabel: elt.dataset.confirmCancelLabel,
    onConfirm: () => detail.issueRequest(true),
  })
}

// Guard against Vite HMR stacking duplicates when this module is re-evaluated.
document.removeEventListener("htmx:confirm", handleHtmxConfirm)
document.addEventListener("htmx:confirm", handleHtmxConfirm)
