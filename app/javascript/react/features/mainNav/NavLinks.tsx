import { useRef, useState } from "react"

import { useActiveRoute } from "~/react/shared/hooks/useActiveRoute"
import { useHotkeyInstall } from "~/react/shared/hooks/useHotkeyInstall"
import { NavLink } from "~/react/shared/NavLink"
import { activeNavItem, NAV_ITEMS } from "./items"
import { SlidingIndicator } from "./SlidingIndicator"

export function NavLinks() {
  const navRef = useRef<HTMLElement>(null)
  const pathname = useActiveRoute()
  const [hoveredHref, setHoveredHref] = useState<string | null>(null)

  useHotkeyInstall(navRef)

  const active = activeNavItem(pathname)
  // Sections like /meetings don't match any of the 5 tabs — the indicator hides
  // (width 0) and no link gets aria-current. Hovering still previews the bar.
  const targetHref = hoveredHref ?? active?.href ?? ""
  const hovering = hoveredHref !== null && hoveredHref !== active?.href

  return (
    <nav
      ref={navRef}
      aria-label="Main"
      className="relative flex items-center"
      onMouseLeave={() => setHoveredHref(null)}
    >
      <SlidingIndicator
        containerRef={navRef}
        targetSelector={targetHref ? `[data-nav-href="${cssEscape(targetHref)}"]` : "[data-no-match]"}
        hovering={hovering}
      />
      {NAV_ITEMS.map(item => {
        const isActive = item.href === active?.href
        return (
          <NavLink
            key={item.href}
            href={item.href}
            prefetch
            clientRouted={item.clientRouted}
            data-nav-href={item.href}
            data-hotkey={item.hotkey}
            aria-current={isActive ? "page" : undefined}
            onMouseEnter={() => setHoveredHref(item.href)}
            className={`px-2 sm:px-3 py-1.5 text-sm transition-colors duration-200 ${
              isActive ? "text-primary font-medium" : "text-base-content hover:text-primary"
            }`}
            style={{ transitionTimingFunction: "var(--ease-snappy)" }}
          >
            {item.label}
          </NavLink>
        )
      })}
    </nav>
  )
}

// CSS.escape covers attribute selectors safely. The hrefs here are simple
// (/, /chats, /posts, …) but escaping keeps the selector robust if hrefs
// ever gain query strings or special characters.
function cssEscape(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value)
  }
  return value.replace(/(["\\])/g, "\\$1")
}
