// Per-route container width for the AppShell, mirroring the Jinja
// `wrapper_classes` map in layouts/application.html.jinja. A route opts into a
// width via its `staticData.shellWidth`; unset falls back to "narrow", matching
// the server's `wrapper|default('narrow')`.

export type ShellWidth = "full" | "medium" | "narrow"

export const DEFAULT_SHELL_WIDTH: ShellWidth = "narrow"

// Make `staticData.shellWidth` type-safe (and typo-proof) on every createRoute
// call, the same way router.tsx augments `Register`. One contract, enforced at
// the route definitions rather than only at the resolver below. (The boolean
// chrome opt-ins on the same interface — hideMobileNav, clipContainerOverflowX,
// showGmailReauthBadge — are declared in shellRouteFlags.ts; TypeScript merges
// the two declarations.)
declare module "@tanstack/react-router" {
  interface StaticDataRouteOption {
    shellWidth?: ShellWidth
  }
}

// Resolve the active width from the matched route chain. The deepest match with
// an explicit shellWidth wins, so a leaf route overrides a layout default.
export function resolveShellWidth(matches: readonly { staticData?: { shellWidth?: ShellWidth } }[]): ShellWidth {
  for (let i = matches.length - 1; i >= 0; i--) {
    const width = matches[i]?.staticData?.shellWidth
    if (width) return width
  }
  return DEFAULT_SHELL_WIDTH
}

// Mirrors the Jinja wrapper_classes map in layouts/application.html.jinja. The
// `page-content` marker opts narrow/medium pages into the top gap below the nav
// (main.css owns the rule); full-width pages carry no marker and no gap.
export function shellWidthClassName(width: ShellWidth): string {
  switch (width) {
    case "full":
      return "w-full"
    case "medium":
      return "page-content w-full max-w-screen-xl mx-auto pb-12"
    case "narrow":
      return "page-content w-full max-w-4xl mx-auto pb-12"
  }
}
