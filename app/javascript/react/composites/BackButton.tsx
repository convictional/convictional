import { install, uninstall } from "@github/hotkey"
import { useEffect, useRef } from "react"

import { NavLink } from "~/react/shared/NavLink"
import type { BackNavigation } from "~/react/shared/types"

// The single back affordance for every show page (goal, post, chat, email
// thread, document, meeting). Server-computed `back` ({ url, label }) drives it;
// the only real variance across pages is whether the label shows and whether the
// target client-routes, so those are the only knobs. No visual tooltip — an
// arrow + "Back to X" is self-explanatory.
interface BackButtonProps {
  back: BackNavigation
  // Icon-only (btn-square), for dense toolbars where a text label is noise
  // (email thread, chat, document editor). Otherwise the label rides alongside
  // the icon on sm+ and hides on mobile to stay compact.
  iconOnly?: boolean
  // Render a NavLink so the target client-routes when it's a registered SPA
  // path (documents); a plain <a> full-document navigates everywhere else.
  navLink?: boolean
  // Disable the `u` hotkey while an overlay should swallow keys (e.g. the
  // mailbox snooze popover, where `u` must dismiss rather than navigate back).
  hotkeyEnabled?: boolean
  className?: string
}

export function BackButton({
  back,
  iconOnly = false,
  navLink = false,
  hotkeyEnabled = true,
  className,
}: BackButtonProps) {
  const wrapperRef = useRef<HTMLSpanElement>(null)

  // Install the `u` hotkey directly on the rendered anchor rather than via a
  // `data-hotkey` attribute: show islands don't run the global initializer, and
  // an attribute would be double-registered inside containers that already scan
  // their subtree (MailboxActionBar). display:contents keeps the wrapper out of
  // layout, and querySelector reaches the anchor whether it's an <a> or the
  // <a> NavLink renders.
  useEffect(() => {
    if (!hotkeyEnabled) return
    const anchor = wrapperRef.current?.querySelector("a")
    if (!anchor) return
    install(anchor, "u")
    return () => uninstall(anchor)
  }, [hotkeyEnabled])

  const classes = `btn${iconOnly ? " btn-square" : ""}${className ? ` ${className}` : ""}`
  const content = (
    <>
      <span className="material-symbols-outlined text-lg">arrow_back</span>
      {!iconOnly && <span className="hidden sm:inline">{back.label}</span>}
    </>
  )

  return (
    <span ref={wrapperRef} style={{ display: "contents" }}>
      {navLink ? (
        <NavLink href={back.url} className={classes} aria-label={back.label} data-testid="back-button">
          {content}
        </NavLink>
      ) : (
        <a href={back.url} className={classes} aria-label={back.label} data-testid="back-button">
          {content}
        </a>
      )}
    </span>
  )
}
