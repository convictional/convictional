import { useEffect, useState } from "react"

// Show pages opt out of the mobile nav chrome by declaring the nav hidden. Both
// stacks funnel that fact through one bus — `data-mobile-nav="hidden"` on
// #container: legacy Jinja emits it server-side (layouts/application.html.jinja),
// the SPA shell derives it from `hideMobileNav` (AppShell). main.css zeroes the
// --mobile-nav-* vars off the same attribute, so it is the single source of truth
// for whether the nav is hidden. The attribute lives on #container rather than
// <body> because hx-boost swaps body innerHTML, so a body attribute would go
// stale after the first boost navigation, while #container is re-rendered by
// every swap.
function readMobileNavHidden(): boolean {
  return document.getElementById("container")?.dataset.mobileNav === "hidden"
}

// Returns whether the current page declared the mobile nav hidden. The nav island
// is hx-preserve'd (legacy) / always mounted (SPA), so the value must re-read when
// the page changes — via two mechanisms that cover both stacks:
//   - Legacy hx-boost replaces #container with a fresh element on each navigation
//     (no in-place mutation), so re-read + re-observe on htmx:afterSettle and
//     popstate — same triggers useActiveRoute uses.
//   - The SPA keeps one #container and mutates the attribute in place, firing no
//     htmx/popstate event, so a MutationObserver on the attribute is what keeps it
//     correct there.
export function useMobileNavHidden(): boolean {
  const [hidden, setHidden] = useState(() => (typeof document === "undefined" ? false : readMobileNavHidden()))

  useEffect(() => {
    const observer = new MutationObserver(() => setHidden(readMobileNavHidden()))
    const sync = () => {
      setHidden(readMobileNavHidden())
      // Re-point at the current #container: legacy boost swaps it for a new node,
      // leaving a prior observation watching a detached element.
      observer.disconnect()
      const container = document.getElementById("container")
      if (container) observer.observe(container, { attributes: true, attributeFilter: ["data-mobile-nav"] })
    }
    sync()
    window.addEventListener("popstate", sync)
    document.addEventListener("htmx:afterSettle", sync)
    return () => {
      observer.disconnect()
      window.removeEventListener("popstate", sync)
      document.removeEventListener("htmx:afterSettle", sync)
    }
  }, [])

  return hidden
}
