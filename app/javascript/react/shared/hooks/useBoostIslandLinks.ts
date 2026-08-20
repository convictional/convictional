import { type RefObject, useEffect } from "react"

import { useOptionalRouter } from "~/react/shared/hooks/useOptionalRouter"

// htmx wires hx-boost click handlers only for anchors present during its DOM
// scan, so links rendered by a React island are invisible to it and clicks fall
// through to full-document (hard) navigations. Each hard navigation strands the
// prior page's realm in the renderer until a lazy Blink GC; across many
// navigations they stack toward an OOM crash (#8744). Calling htmx.process() on
// the island root registers boost handlers on its anchors, so navigating between
// islands stays in one realm (React unmounts via mountIsland's htmx:beforeSwap).
// MainNav uses the same idiom for the app nav.
//
// The SPA shell routes with TanStack <Link>s and has no htmx, so this must not
// run there — `useOptionalRouter()` is the island-vs-shell discriminator. Pass
// `deps` that change when the island renders more anchors (e.g. the entry list
// growing) so those late anchors get registered too.
export function useBoostIslandLinks(rootRef: RefObject<HTMLElement | null>, deps: unknown[] = []) {
  const router = useOptionalRouter()
  useEffect(() => {
    if (router) return
    if (rootRef.current && window.htmx) window.htmx.process(rootRef.current)
    // rootRef is stable; re-run when island mode or the caller's deps change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, ...deps])
}
