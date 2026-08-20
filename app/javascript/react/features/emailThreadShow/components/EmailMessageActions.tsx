import { useRef } from "react"

import { useHotkeyInstall } from "~/react/shared/hooks/useHotkeyInstall"

interface EmailMessageActionsProps {
  onReply: () => void
  onReplyAll: () => void
  onForward: () => void
}

// The email-thread island never runs the global hotkey initializer, so this
// component installs its own r / a / f `data-hotkey` buttons on mount via
// useHotkeyInstall.
export function EmailMessageActions({ onReply, onReplyAll, onForward }: EmailMessageActionsProps) {
  const ref = useRef<HTMLDivElement>(null)
  useHotkeyInstall(ref)

  return (
    <div ref={ref} className="p-2 flex justify-between gap-2 rounded-b-xl overflow-hidden border-t border-base-300">
      <div className="flex gap-1">
        <button type="button" className="btn btn-primary" data-hotkey="r" onClick={onReply}>
          <span className="material-symbols-outlined text-base">reply</span>Reply
        </button>
        <button type="button" className="btn btn-ghost text-info-content" data-hotkey="a" onClick={onReplyAll}>
          <span className="material-symbols-outlined text-base">reply_all</span>Reply All
        </button>
      </div>
      <button type="button" className="btn btn-ghost text-info-content" data-hotkey="f" onClick={onForward}>
        <span className="material-symbols-outlined text-base">forward</span>Forward
      </button>
    </div>
  )
}
