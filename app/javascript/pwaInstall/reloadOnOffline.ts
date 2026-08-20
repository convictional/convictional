// HTMX-boosted nav links and AJAX swaps make XHR requests, not top-level
// navigations, so the service worker's navigate-only fetch handler can't
// intercept them. When such a request fails while the browser reports we're
// offline, force a full reload — the resulting navigation is what the SW
// catches and serves the offline page for. We gate on `navigator.onLine`
// so a transient server error (DNS blip, 5xx) doesn't trigger a reload loop;
// 5xx responses fire `htmx:responseError`, not `sendError`, so they're not
// in scope here either.
export function reloadOnOffline() {
  document.addEventListener("htmx:sendError", () => {
    if (!navigator.onLine) location.reload()
  })
}
