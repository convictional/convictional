import type { ReactNode } from "react"

import { Tooltip } from "~/react/ui/Tooltip"

import { MAILBOX_ACTION_SEGMENT_CLASS } from "./segments"

interface MailboxSegmentButtonProps {
  icon: string
  // aria-label, and the tooltip text unless `tooltip` overrides it (e.g. the
  // unsnooze button labels itself "Unsnooze" but tooltips the snoozed-until time).
  label: string
  tooltip?: ReactNode
  onClick?: () => void
  disabled?: boolean
  // data-hotkey binding (e.g. "ArrowLeft"), picked up by the action bar's
  // useHotkeyInstall. Dropped while disabled so an end-of-list arrow doesn't fire.
  hotkey?: string
  // Swap the icon for a spinner and block interaction — a pending boundary fetch.
  loading?: boolean
  // Extra button classes layered onto the segment base (e.g. "text-primary").
  className?: string
  // Icon size utility; defaults to text-lg (unsnooze uses text-xl).
  iconClassName?: string
}

// A flat icon button in the mailbox action bar's joined cluster — the shared
// shape behind mark-read/unread, unsnooze, and the prev/next nav arrows. Mirrors
// the editor's ToolButton: owns the button + tooltip + icon markup so callers
// pass intent (icon/label/handler), not repeated class strings.
export function MailboxSegmentButton({
  icon,
  label,
  tooltip,
  onClick,
  disabled = false,
  hotkey,
  loading = false,
  className = "",
  iconClassName = "text-lg",
}: MailboxSegmentButtonProps) {
  const isDisabled = disabled || loading
  return (
    <Tooltip content={tooltip ?? label} placement="bottom">
      <button
        type="button"
        aria-label={label}
        className={className ? `${MAILBOX_ACTION_SEGMENT_CLASS} ${className}` : MAILBOX_ACTION_SEGMENT_CLASS}
        disabled={isDisabled}
        {...(hotkey && !isDisabled ? { "data-hotkey": hotkey } : {})}
        onClick={isDisabled ? undefined : onClick}
      >
        {loading ? (
          <span className="loading loading-spinner loading-xs" />
        ) : (
          <span className={`material-symbols-outlined ${iconClassName}`}>{icon}</span>
        )}
      </button>
    </Tooltip>
  )
}
