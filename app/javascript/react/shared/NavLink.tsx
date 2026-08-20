import { Link, type RegisteredRouter } from "@tanstack/react-router"
import type { AnchorHTMLAttributes, ReactNode } from "react"

import { useOptionalRouter } from "~/react/shared/hooks/useOptionalRouter"
import { splitHref } from "~/react/shared/urls"

// Dual-mode navigation primitive: the same nav renders both as an island (no
// router context) and inside the SPA shell's RouterProvider, so a link can't
// commit to one navigation mechanism. It branches purely on router context:
//
// - No router context: a plain anchor, with click and hover-prefetch wired
//   externally by the island's host.
// - Router context, path has a registered client route: a TanStack <Link> for
//   client navigation, using the router's "intent" prefetch.
// - Router context, path with no registered route: a plain anchor that does a
//   full-document load.
//
// Shared chrome (command palette, search results) reuses this, so it lives in
// shared/.

type AnchorPassthrough = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">

export interface NavLinkProps extends AnchorPassthrough {
  href: string
  // Prefetch on hover/intent: htmx `preload="mouseover"` in island mode, the
  // router's "intent" preload for registered routes in shell mode. Plain
  // full-document anchors never prefetch (nothing to prefetch client-side).
  prefetch?: boolean
  // The destination is served by the SPA shell — a standalone full document, not
  // a boostable fragment. In island mode htmx would otherwise boost this anchor
  // and fetch the shell over AJAX; opting out keeps the click a native
  // navigation that loads the shell in one request. No effect in shell mode,
  // where a registered path already routes through a client <Link> below.
  clientRouted?: boolean
  children?: ReactNode
}

// `routesByPath` is keyed by trimmed full path and excludes the root and
// pathless layout routes (router-core's processRouteTree skips index 0 and
// routes without a `path`), so membership is exactly "has a registered client
// page". Matching is on the pathname only — query/hash never participate. An index
// route registers under its full path too, so `/` (the Inbox tab) is a member.
// Parameterized routes are keyed by their template (`/documents/$documentId`), so a
// concrete `/documents/abc` is not a member — those callers use a typed <Link>
// directly.
function isClientRoute(router: RegisteredRouter, pathname: string): boolean {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname
  return path in router.routesByPath
}

export function NavLink({ href, prefetch = false, clientRouted = false, children, ...anchorProps }: NavLinkProps) {
  const router = useOptionalRouter()
  const { pathname, search, hash } = splitHref(href)

  if (router && isClientRoute(router, pathname)) {
    const hasSearch = Object.keys(search).length > 0
    return (
      <Link
        to={pathname}
        search={hasSearch ? search : undefined}
        hash={hash || undefined}
        preload={prefetch ? "intent" : false}
        {...anchorProps}
      >
        {children}
      </Link>
    )
  }

  // Island mode keeps htmx's hover prefetch; shell-mode unregistered paths get a
  // bare anchor (no client route to prefetch). clientRouted links skip the
  // preload: with hx-boost off the hover XHR only warms a wasted 204, never the
  // shell that the native click actually loads.
  const preloadAttr = !router && prefetch && !clientRouted ? { preload: "mouseover" } : {}
  // hx-boost="false" makes htmx.process() skip this anchor so the click is a
  // native navigation rather than a boosted fragment fetch of the SPA shell.
  const boostAttr = !router && clientRouted ? { "hx-boost": "false" } : {}
  return (
    <a href={href} {...preloadAttr} {...boostAttr} {...anchorProps}>
      {children}
    </a>
  )
}
