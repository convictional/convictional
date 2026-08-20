import { useEffect, useState } from "react"

import { type Toast, toastStore } from "~/react/shared/stores/toast"

const AUTO_DISMISS_MS = 3000
// Matches the leave transition duration below so the node is removed only after
// the exit animation finishes.
const LEAVE_MS = 200

// Only follow http(s) or same-origin relative URLs. Guards the click-through
// against a `javascript:`/`data:` scheme smuggled in via a flash `url`, which
// would otherwise execute when assigned to window.location.
function isSafeNavigationUrl(url: string): boolean {
  if (url.startsWith("/")) return true
  try {
    const { protocol } = new URL(url, window.location.origin)
    return protocol === "http:" || protocol === "https:"
  } catch {
    return false
  }
}

export function ToastItem({ toast }: { toast: Toast }) {
  const { id, message, level, url, persistent } = toast
  const isError = level === "error"

  // `visible` drives the enter/leave transition: false on first paint, flipped
  // true next frame to animate in, then false to animate out before the store
  // drops the toast.
  const [visible, setVisible] = useState(false)

  const startDismiss = () => {
    setVisible(false)
    setTimeout(() => toastStore.getState().dismiss(id), LEAVE_MS)
  }

  useEffect(() => {
    const enter = requestAnimationFrame(() => setVisible(true))
    if (persistent) return () => cancelAnimationFrame(enter)

    let removeTimer: ReturnType<typeof setTimeout>
    const dismissTimer = setTimeout(() => {
      setVisible(false)
      removeTimer = setTimeout(() => toastStore.getState().dismiss(id), LEAVE_MS)
    }, AUTO_DISMISS_MS)

    return () => {
      cancelAnimationFrame(enter)
      clearTimeout(dismissTimer)
      clearTimeout(removeTimer)
    }
  }, [id, persistent])

  const handleCardClick = () => {
    if (url && isSafeNavigationUrl(url)) {
      window.location.href = url
      return
    }
    startDismiss()
  }

  const enterClasses = visible ? "opacity-100 translate-y-0 scale-100" : "opacity-0 translate-y-4 scale-95"
  // Enter pops in over 400ms; leave fades out over 200ms (LEAVE_MS) so the node
  // is removed exactly when the exit animation finishes.
  const transitionClasses = visible
    ? "transition ease-[var(--ease-pop)] duration-400"
    : "transition ease-in duration-200"

  return (
    <div
      onClick={handleCardClick}
      // role/aria-live announce the toast on insertion: errors interrupt
      // (assertive), successes wait their turn (polite).
      role={isError ? "alert" : "status"}
      aria-live={isError ? "assertive" : "polite"}
      className={`dropdown-card cursor-pointer self-center max-w-[calc(100dvw-2rem)] ${transitionClasses} ${enterClasses}`}
    >
      <div className="relative overflow-hidden rounded-xl">
        {!persistent && (
          <div
            className={`absolute inset-0 ${isError ? "bg-error/40" : "bg-success/40"} w-0 animate-[fillBar_3s_linear_forwards]`}
          />
        )}
        <div
          className={`relative grid grid-cols-[auto_1fr_auto] items-center gap-2 px-2 py-0 ${isError ? "text-error-content bg-error/20" : "text-success-content bg-success/20"}`}
        >
          <span className="material-symbols-outlined text-lg" aria-hidden="true">
            {isError ? "error" : "check"}
          </span>
          <span className="text-xs py-1">{message}</span>
          {/* Real button so the toast — including the persistent CSRF one — is
              dismissable by keyboard, not just mouse. */}
          <button
            type="button"
            aria-label="Dismiss"
            onClick={event => {
              event.stopPropagation()
              startDismiss()
            }}
            className="material-symbols-outlined text-base text-base-500 cursor-pointer bg-transparent"
          >
            close
          </button>
        </div>
      </div>
    </div>
  )
}
