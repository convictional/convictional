import { toastStore } from "~/react/shared/stores/toast"
import { TOAST_EVENT, type ToastEventDetail } from "~/shared/flash"

// Bridges the framework-agnostic showFlash() window event into the Zustand
// store. The store stays decoupled from the DOM event; flash.ts stays decoupled
// from React. Guarded so multiple callers attach the listener at most once
// per document.
let registered = false

export function registerToastEventBridge(): void {
  if (registered) return
  registered = true
  window.addEventListener(TOAST_EVENT, event => {
    const { message, level, url, persistent } = (event as CustomEvent<ToastEventDetail>).detail
    toastStore.getState().show({ message, level, url, persistent })
  })
}
