// Navigate within the app without tearing down the JS realm.
//
// A hard navigation (window.location) destroys the current realm. Any fetch
// still in flight is rejected by the browser with "TypeError: Failed to fetch",
// and that rejection's reaction microtask can't drain before the realm is gone —
// so it strands in the microtask queue and pins the whole dead realm (its
// NativeContext, Window, detached document, and ~11 MB of duplicated compiled
// code/shapes). Across many navigations the stranded realms stack toward an OOM
// crash (#8744). A heap snapshot confirmed ~20 realms pinned this exact way,
// one per hard navigation.
//
// Boosted navigation avoids it: <body hx-boost="true"> makes htmx swap the body
// in place, so the realm is never torn down — React unmounts cleanly and any
// aborted fetch settles while the realm is still pumping microtasks. Synthesizing
// a boosted anchor click runs the identical code path a real in-app link takes,
// rather than reimplementing boost's target/swap/history handling. Cross-origin
// URLs (external meeting links) and non-htmx contexts (the SPA shell, which
// routes via TanStack) fall back to a full-document navigation.
export function boostedNavigate(url: string): void {
  if (typeof window !== "undefined" && window.htmx && isSameOrigin(url)) {
    const link = document.createElement("a")
    link.href = url
    // Append before process so htmx sees the hx-boost="true" inherited from
    // <body>. The click runs htmx's boost handler synchronously (it targets
    // <body>, not the anchor), so the detached anchor is safe to drop right after.
    document.body.appendChild(link)
    window.htmx.process(link)
    link.click()
    link.remove()
    return
  }
  window.location.href = url
}

function isSameOrigin(url: string): boolean {
  try {
    return new URL(url, window.location.origin).origin === window.location.origin
  } catch {
    return false
  }
}
