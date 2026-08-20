import { describe, expect, test } from "vitest"

import { router } from "~/react/app/router"

// TanStack stores children as an array or a keyed record depending on how the
// tree was composed; normalize to an array for assertions.
function childrenOf(route: { children?: unknown }): {
  id: string
  path?: string
  options?: { staticData?: { showGmailReauthBadge?: boolean } }
}[] {
  const children = route.children
  if (!children) return []
  return Array.isArray(children) ? children : Object.values(children)
}

describe("app router", () => {
  test("mounts the AppShell layout route under the root", () => {
    expect(router).toBeDefined()
    expect(typeof router.navigate).toBe("function")

    // The pathless AppShell layout route is the sole child of the root.
    expect(childrenOf(router.routeTree)).toHaveLength(1)
  })

  test("registers the notifications page as a child of the shell route", () => {
    const [shell] = childrenOf(router.routeTree)
    expect(shell.id).toBe("/shell")
    expect(childrenOf(shell).map(r => r.id)).toContain("/shell/notifications")
  })

  test("gates the Gmail reauth badge to the mailbox/email routes, never /unread", () => {
    const [shell] = childrenOf(router.routeTree)
    const badgeRoutes = new Set(
      childrenOf(shell)
        .filter(r => r.options?.staticData?.showGmailReauthBadge)
        .map(r => r.id)
    )
    // Mirrors the legacy GMAIL_REAUTH_BADGE_ROUTES list (integrations/google/helpers.py):
    // every mailbox view except /unread, plus the email-thread show page.
    expect(badgeRoutes).toEqual(
      new Set([
        "/shell/",
        "/shell/archived",
        "/shell/sent",
        "/shell/drafts",
        "/shell/assigned_to_me",
        "/shell/snoozed",
        "/shell/email_threads/$emailThreadId",
      ])
    )
    expect(badgeRoutes.has("/shell/unread")).toBe(false)
  })

  test("enables scroll restoration and intent preloading", () => {
    expect(router.options.scrollRestoration).toBe(true)
    expect(router.options.defaultPreload).toBe("intent")
  })
})
