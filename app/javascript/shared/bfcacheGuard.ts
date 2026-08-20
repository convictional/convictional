// Guards against the browser back/forward cache (bfcache) restoring an
// authenticated page after the user has logged out. This replaced the old
// `Clear-Site-Data: "cache"` logout header, which made WebKit freeze the origin
// network while clearing storage (a ~70s logout hang in Safari).
//
// The backend sets a JS-readable `logged_in=1` marker cookie while an
// authenticated session exists and expires it on logout. On a bfcache restore
// the body's `data-authenticated` reflects the cached snapshot while
// `document.cookie` reflects live cookies — so a missing marker means the
// cached page is stale and we force a fresh load to land on /login.

// True only if there is a cookie named exactly `logged_in` with value `1`.
// Parse the cookie pairs rather than substring-matching so we don't match
// e.g. `xlogged_in=1` or `logged_in=10`.
export function isLoggedInMarkerPresent(): boolean {
  return document.cookie.split("; ").some(pair => pair === "logged_in=1")
}

// `event.persisted` is only true on a bfcache restore, so normal loads are
// untouched. Returns an unsubscribe function so tests can remove the listener;
// the boot call site at main.ts ignores it.
export function installBfcacheGuard(): () => void {
  const handler = (event: PageTransitionEvent) => {
    if (event.persisted && document.body.dataset.authenticated === "true" && !isLoggedInMarkerPresent()) {
      location.reload()
    }
  }
  window.addEventListener("pageshow", handler)
  return () => window.removeEventListener("pageshow", handler)
}
