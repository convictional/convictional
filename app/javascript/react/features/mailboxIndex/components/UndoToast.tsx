import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { formatSnoozedUntil } from "~/react/ui/DateTime"

interface UndoToastProps {
  action: "archive" | "snooze" | null
  onUndo: () => void
  // Present for the snooze action; formatted into the confirmation in the user's timezone.
  snoozedUntil?: string
  timezone?: string | null
}

export function UndoToast({ action, onUndo, snoozedUntil, timezone }: UndoToastProps) {
  const isMobile = useIsMobile()
  if (!action) return null
  const label = action === "snooze" ? formatSnoozedUntil(snoozedUntil, timezone) : "Archived"
  // Clear the mobile pill nav. --mobile-nav-offset self-zeroes on nav-hidden
  // pages (main.css keys it off #container's data-mobile-nav), so it reserves
  // space only when the pill shows; desktop has no pill.
  const bottomClass = isMobile
    ? "bottom-[max(var(--mobile-nav-offset),1rem,var(--safe-area-inset-bottom))]"
    : "bottom-[max(1rem,var(--safe-area-inset-bottom))]"
  return (
    <div
      className={`fixed ${bottomClass} left-1/2 -translate-x-1/2 z-50 lg:ml-7 dropdown-card cursor-pointer max-w-[calc(100dvw-2rem)]`}
    >
      <div className="relative overflow-hidden rounded-xl">
        <div
          data-test-id="undo-progress-bar"
          className="absolute inset-0 bg-info-content/15 w-0 animate-[fillBar_8s_linear_forwards]"
        />
        <div className="relative grid grid-cols-[1fr_auto] items-center gap-2 px-2 py-0 text-info-content bg-info-content/10">
          <span className="text-xs py-1">{label}</span>
          <button
            type="button"
            className="btn btn-sm btn-ghost text-xs font-semibold text-info-content hover:bg-info-content/15"
            onClick={e => {
              e.stopPropagation()
              onUndo()
            }}
          >
            Undo
          </button>
        </div>
      </div>
    </div>
  )
}
