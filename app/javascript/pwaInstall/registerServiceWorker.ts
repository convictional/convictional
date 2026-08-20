export function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    return
  }

  window.addEventListener("load", () => {
    // The service worker is a progressive enhancement (installable PWA, offline
    // page, web push); the app is fully functional without it. register() can
    // reject for client-environment reasons we neither control nor need to
    // support here — private browsing, or storage/service workers disabled by
    // browser or enterprise policy. Those failures are non-actionable, so
    // handle the rejection instead of letting it escape as an unhandled promise
    // rejection.
    navigator.serviceWorker.register("/service-worker.js").catch(() => {})
  })
}
