import { FloatingPortal } from "@floating-ui/react"
import { type ReactNode, useEffect, useState } from "react"

import { FLOATING_PORTAL_ROOT_ID } from "~/react/ui/floatingPortalRoot"

// A long-press opens an action sheet while the finger is still down, and iOS
// fires a synthetic click when it lifts — which would land on the freshly-mounted
// sheet (tapping an action or dismissing via the backdrop). This returns a
// pointer-blocking shield to render alongside the sheet; it stays up until the
// originating touch ends (plus a beat for the click), with a generous timeout as
// a backstop. Shared by the chat and comment action sheets — the only sheets
// opened by long-press rather than a tap, so the only ones that need it.
//
// The shield renders into the sheet's FloatingPortal so its z-[80] sits above the
// panel (z-[70]) and backdrop (z-[60]).
export function useLongPressSheetShield(): { shield: ReactNode } {
  // The press finger is still down at mount and iOS fires the click when it
  // lifts, so a fixed timer can drop the shield too early — hold until the touch
  // ends instead.
  const [isReady, setIsReady] = useState(false)
  useEffect(() => {
    let settleTimer = 0
    let fallbackTimer = 0
    // The press is touch-originated (useLongPress is touch-only), so wait for
    // every finger to lift — a touchend that still leaves `touches` non-empty is
    // a second finger releasing while the press finger is held, and dropping the
    // shield then would let that held finger's eventual synthetic click land on
    // the now-unguarded sheet. touchcancel covers an interrupted gesture.
    const onRelease = (e: TouchEvent) => {
      if (e.touches?.length) return
      window.removeEventListener("touchend", onRelease)
      window.removeEventListener("touchcancel", onRelease)
      clearTimeout(fallbackTimer)
      settleTimer = window.setTimeout(() => setIsReady(true), 100)
    }
    window.addEventListener("touchend", onRelease)
    window.addEventListener("touchcancel", onRelease)
    fallbackTimer = window.setTimeout(() => setIsReady(true), 1500)
    return () => {
      window.removeEventListener("touchend", onRelease)
      window.removeEventListener("touchcancel", onRelease)
      clearTimeout(fallbackTimer)
      clearTimeout(settleTimer)
    }
  }, [])

  const shield = isReady ? null : (
    <FloatingPortal id={FLOATING_PORTAL_ROOT_ID}>
      <div className="fixed inset-0 z-[80]" aria-hidden="true" />
    </FloatingPortal>
  )

  return { shield }
}
