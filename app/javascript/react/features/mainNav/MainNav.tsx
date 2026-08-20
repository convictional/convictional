import { useEffect, useRef } from "react"

import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useMobileNavHidden } from "~/react/shared/hooks/useMobileNavHidden"
import { useOptionalRouter } from "~/react/shared/hooks/useOptionalRouter"
import { useRevealNavOnScroll } from "~/react/shared/hooks/useRevealNavOnScroll"

import { MeetingsNavMenu } from "./MeetingsNavMenu"
import { MobileBottomNav } from "./MobileBottomNav"
import { MobileSearchOverlay } from "./MobileSearchOverlay"
import { MobileTopBar } from "./MobileTopBar"
import { MoreMenu } from "./MoreMenu"
import { NavLinks } from "./NavLinks"
import { ResearchButton } from "./ResearchButton"
import { SearchButton } from "./SearchButton"

export interface MainNavProps {
  isAdmin: boolean
  isSuperuser: boolean
  organizationName: string | null
}

export function MainNav({ isAdmin, isSuperuser, organizationName }: MainNavProps) {
  const isMobile = useIsMobile()
  const rootRef = useRef<HTMLDivElement>(null)
  // Show pages declare the nav hidden via the `mobile_nav_hidden` template
  // flag so they can use the full viewport; the CSS vars are zeroed by
  // main.css off the same attribute.
  const hideMobileNav = useMobileNavHidden()
  // Present only in the SPA shell; undefined on legacy Jinja pages (island mode).
  const router = useOptionalRouter()

  // Reveal-on-scroll-up for the whole app: this island is always mounted and
  // hx-preserve'd, so one controller here drives the nav on every page. Desktop
  // only — mobile hides the top nav wrapper and uses the bottom tab bar.
  useRevealNavOnScroll(!isMobile)

  // Island mode only: htmx wires boost listeners during its initial scan, so
  // React-rendered anchors are invisible to it and clicks fall through to full
  // page reloads. htmx.process() registers them on mount. The shell uses router
  // <Link>s and has no htmx, so this must not run there.
  useEffect(() => {
    if (router) return
    if (rootRef.current && window.htmx) {
      window.htmx.process(rootRef.current)
    }
  }, [router])

  if (isMobile) {
    return (
      <div ref={rootRef}>
        {!hideMobileNav && <MobileTopBar />}
        {!hideMobileNav && (
          <MobileBottomNav isAdmin={isAdmin} isSuperuser={isSuperuser} organizationName={organizationName} />
        )}
        <MobileSearchOverlay />
      </div>
    )
  }

  return (
    <div ref={rootRef} className="w-full flex justify-between items-center gap-2 overflow-x-auto">
      <NavLinks />
      <div className="flex items-center gap-2">
        <div className="flex items-center max-w-[200px] bg-base-200 border border-base-300 rounded-full p-0.5 transition-colors">
          <MeetingsNavMenu />
        </div>
        <div className="flex items-center bg-base-200 border border-base-300 rounded-full p-0.5 transition-colors">
          <SearchButton />
          <div className="w-px h-5 bg-base-300" />
          <ResearchButton />
        </div>
        <MoreMenu isAdmin={isAdmin} isSuperuser={isSuperuser} organizationName={organizationName} />
      </div>
    </div>
  )
}
