// Two distinct server contracts, both expressed as query params on a target URL:
//
//   - `return_to`  — the content "back" link (resolved by back_navigation() and
//     friends on content pages like documents/posts/mailbox entries).
//   - `redirect_to` — the post-authentication redirect target (resolved by
//     Helpers.redirect_from_request / redirect_back_or, and mirrored by the
//     server's session-based remember_location()).
//
// They are not interchangeable: the login guard uses `redirect_to`, content
// back-links use `return_to`.

function withParam(param: string, href: string, currentUrl: string): string {
  try {
    const url = new URL(href, currentUrl)
    const current = new URL(currentUrl)
    url.searchParams.set(param, current.pathname + current.search)
    return url.pathname + url.search + url.hash
  } catch {
    // URL constructor throws for unusable bases (e.g. jsdom defaults to
    // about:blank). Skip the rewrite rather than bringing the page down.
    return href
  }
}

export function withReturnTo(href: string, currentUrl: string = window.location.href): string {
  return withParam("return_to", href, currentUrl)
}

// `return_to` is attacker-controllable (it rides the URL), so only same-origin
// relative paths are honored — an absolute or protocol-relative URL (`//evil.com`)
// would turn a back link or a forwarded redirect into an open redirect. This is
// the read-side guard, shared so the open-redirect defense lives in exactly one
// place; `withReturnTo` above is the write side.
export function safeReturnTo(returnTo: string | undefined): string | undefined {
  return returnTo && returnTo.startsWith("/") && !returnTo.startsWith("//") ? returnTo : undefined
}

export function withRedirectTo(href: string, currentUrl: string = window.location.href): string {
  return withParam("redirect_to", href, currentUrl)
}
