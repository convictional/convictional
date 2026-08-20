// Per-route boolean opt-ins the AppShell reads off the matched route chain to
// decide chrome. Each is off by default; a route turns one on via its
// `staticData`, and the matching resolver returns true if any matched route in
// the chain opted in. Grouped here so the shell's chrome flags live in one place
// and shellWidth.ts stays about width. (The `StaticDataRouteOption` augmentation
// is deliberately split by concern — shellWidth.ts declares `shellWidth`; these
// three are declared here. TypeScript merges the two declarations.)

declare module "@tanstack/react-router" {
  interface StaticDataRouteOption {
    // Opt the shell #container into horizontal-overflow clipping for this route.
    // Off by default: clipping is global to #container, so a route that wants
    // intentional horizontal scroll (a wide table, a calendar) must not be
    // silently clipped. The document editor opts in because its comment gutter is
    // positioned beyond the content column.
    clipContainerOverflowX?: boolean
    // Suppress the top MainNav and the mobile-nav bottom offset for this route on
    // mobile, so the page is genuinely full-screen (chat show). Parity with the
    // Jinja `mobile_nav_hidden` flag. Ignored on desktop (the nav always shows).
    hideMobileNav?: boolean
    // Show the Gmail reauth badge on this route. Mirrors the legacy
    // GMAIL_REAUTH_BADGE_ROUTES list (integrations/google/helpers.py): the mailbox
    // views and the email-thread show page, but not /unread. The badge only
    // actually renders if the connection needs reauth (GmailReauthBadge owns that).
    showGmailReauthBadge?: boolean
  }
}

// Any matched route in the chain opting in clips #container's horizontal overflow.
export function resolveClipContainerOverflowX(
  matches: readonly { staticData?: { clipContainerOverflowX?: boolean } }[]
): boolean {
  return matches.some(match => match.staticData?.clipContainerOverflowX)
}

// Any matched route in the chain opting in hides the mobile nav.
export function resolveHideMobileNav(matches: readonly { staticData?: { hideMobileNav?: boolean } }[]): boolean {
  return matches.some(match => match.staticData?.hideMobileNav)
}

// Any matched route in the chain opting in shows the Gmail reauth badge.
export function resolveShowGmailReauthBadge(
  matches: readonly { staticData?: { showGmailReauthBadge?: boolean } }[]
): boolean {
  return matches.some(match => match.staticData?.showGmailReauthBadge)
}
