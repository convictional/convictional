import { rootRouteId } from "@tanstack/react-router"
import { useCallback } from "react"

import { boostedNavigate } from "~/react/shared/boostedNavigate"
import { useOptionalRouter } from "~/react/shared/hooks/useOptionalRouter"
import { splitHref } from "~/react/shared/urls"

// Imperative twin of NavLink for code paths that navigate to an href they compute
// (not a rendered link) and that run BOTH as an htmx island and inside the SPA
// shell — e.g. the mailbox prev/next arrows. In the shell, boostedNavigate has no
// htmx and does a full-document reload; that tears down the realm the SPA exists
// to keep alive (#8744). So when the href resolves to a registered client route,
// route through TanStack instead; otherwise (island mode, or a non-SPA target like
// a post/email thread or the inbox) fall back to boostedNavigate.
export function useBoundaryNavigate(): (href: string) => void {
  const router = useOptionalRouter()
  return useCallback(
    (href: string) => {
      if (router) {
        const { pathname, search, hash } = splitHref(href)
        // getMatchedRoutes matches parameterized templates too (unlike NavLink's
        // routesByPath lookup), so a concrete /chats/{id} resolves to its route; a
        // path with no registered route (/profile/edit) fuzzy-matches only the root
        // and is left to a full-document navigation.
        const { foundRoute } = router.getMatchedRoutes(pathname)
        if (foundRoute && foundRoute.id !== rootRouteId) {
          void router.navigate({ to: pathname, search, hash: hash || undefined })
          return
        }
      }
      boostedNavigate(href)
    },
    [router]
  )
}
