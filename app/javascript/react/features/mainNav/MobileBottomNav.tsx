import { useRef, useState } from "react"

import { useActiveRoute } from "~/react/shared/hooks/useActiveRoute"
import { NavLink } from "~/react/shared/NavLink"
import { BottomSheet, type BottomSheetHandle } from "~/react/ui/BottomSheet"
import { activeNavItem, MOBILE_BOTTOM_TAB_ITEMS } from "./items"
import { MobileMoreMenu } from "./MobileMoreMenu"

// Each tab is a fixed-width capsule inset a uniform 6px from the bar edges
// (my-1.5 vertically; mx-0.5 plus the bar's px-1 horizontally). Because both the
// capsule and the bar are rounded-full, that equal inset makes the active tab's
// rounded end nest concentrically inside the bar's rounded end with a constant
// halo, reading as a floating liquid-glass lozenge rather than a clipped rect.
const TAB_CLASS = "mx-0.5 my-1.5 flex w-14 flex-col items-center justify-center gap-0.5 rounded-full transition-colors"

interface MobileBottomNavProps {
  isAdmin: boolean
  isSuperuser: boolean
  organizationName: string | null
}

export function MobileBottomNav({ isAdmin, isSuperuser, organizationName }: MobileBottomNavProps) {
  const pathname = useActiveRoute()
  const active = activeNavItem(pathname)
  const [open, setOpen] = useState(false)
  const sheetRef = useRef<BottomSheetHandle>(null)

  const dismissIfOpen = () => sheetRef.current?.close()

  return (
    <>
      {/* Docked wrapper holds the pill. Containing the pill's shadow inside a
          docked, non-clipping element (rather than on a detached fixed node)
          keeps mobile Safari from clipping it at the browser-chrome edge. */}
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex justify-center">
        <nav
          aria-label="Main"
          className="pointer-events-auto flex h-[var(--mobile-nav-height)] items-stretch overflow-hidden rounded-full border border-base-400 bg-base-300 px-1"
          style={{
            // Bottom gap is a fixed 20px on purpose. It does not add the iOS bottom
            // safe-area inset, which would push the pill too high.
            marginBottom: "var(--mobile-nav-gap)",
            // Depth without transparency: a soft layered drop shadow (ambient +
            // contact) lifts the pill off the page, and an inset top highlight
            // catches light on the rim so it reads as a raised surface, not a
            // flat swatch.
            boxShadow: [
              "0 12px 32px -8px rgba(0, 0, 0, 0.3)",
              "0 4px 10px -4px rgba(0, 0, 0, 0.18)",
              "inset 0 1px 0.5px rgba(255, 255, 255, 0.4)",
            ].join(", "),
          }}
        >
          {MOBILE_BOTTOM_TAB_ITEMS.map(item => {
            const isActive = item.href === active?.href
            return (
              <NavLink
                key={item.href}
                href={item.href}
                onClick={dismissIfOpen}
                className={`${TAB_CLASS} ${
                  isActive ? "bg-base-100 text-base-content" : "text-base-content/50 active:text-base-content/70"
                }`}
                aria-current={isActive ? "page" : undefined}
              >
                <span
                  className="material-symbols-outlined text-[22px]"
                  style={{ fontVariationSettings: isActive ? "'FILL' 1, 'wght' 500" : "'FILL' 0, 'wght' 400" }}
                >
                  {item.icon}
                </span>
                <span className={`text-[10px] leading-tight ${isActive ? "font-medium" : ""}`}>{item.label}</span>
              </NavLink>
            )
          })}
          <button
            type="button"
            onClick={() => setOpen(true)}
            className={`${TAB_CLASS} cursor-pointer text-base-content/50 active:text-base-content/70`}
            aria-label="More navigation options"
            aria-expanded={open}
          >
            <span
              className="material-symbols-outlined text-[22px]"
              style={{ fontVariationSettings: "'FILL' 0, 'wght' 400" }}
            >
              more_horiz
            </span>
            <span className="text-[10px] leading-tight">More</span>
          </button>
        </nav>
      </div>

      {open && (
        <BottomSheet ref={sheetRef} onClose={() => setOpen(false)}>
          <MobileMoreMenu
            isAdmin={isAdmin}
            isSuperuser={isSuperuser}
            organizationName={organizationName}
            onItemClick={dismissIfOpen}
          />
        </BottomSheet>
      )}
    </>
  )
}
