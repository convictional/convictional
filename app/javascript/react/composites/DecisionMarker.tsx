import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import type { Decision } from "~/react/shared/types"
import { formatDateTime } from "~/react/ui/DateTime"
import { Tooltip } from "~/react/ui/Tooltip"

import { UserAvatar } from "./UserAvatar"

interface DecisionMarkerProps {
  // The decision anchored to this comment, if any. Undefined means undecided —
  // render the quiet "Decide" affordance instead of the pill.
  decision: Decision | undefined
  // Single-click toggle: marks when undecided, clears when decided. The island
  // owns the POST/DELETE — this composite carries no API or thread knowledge.
  onToggle: () => void
  // Extra classes for the button, so an island can align the marker with its own
  // reaction row (e.g. matching the reaction strip's top margin).
  className?: string
}

// A reaction-grade decision affordance sized to sit beside a comment's reaction
// row. Two states share one toggle: an undecided comment shows a quiet "Decide"
// button; a decided one shows the green pill with the decider's avatar. Lifted
// from the decisions-162 design (icon alt_route, btn-decision pill).
export function DecisionMarker({ decision, onToggle, className }: DecisionMarkerProps) {
  // The marker decides whether this viewer may undecide without each render site
  // threading identity down. `currentUser` is null until the query resolves.
  const { user: currentUser } = useCurrentUser()

  if (!decision) {
    return (
      <Tooltip content="Decide">
        <button
          type="button"
          className={`btn btn-sm btn-ghost text-base-500 ${className ?? ""}`}
          aria-label="Decide"
          onClick={onToggle}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
            alt_route
          </span>
        </button>
      </Tooltip>
    )
  }

  const decidedBy = decision.decided_by
  // Only the decider or an org admin may clear a decision; the DELETE endpoint
  // enforces the same rule, so this just keeps a member from accidentally
  // undeciding someone else's. Gate on a resolved user so the decider isn't shown
  // an inert pill during the current-user fetch.
  const isUserLoaded = !!currentUser
  const canUndecide = isUserLoaded && (decidedBy?.id === currentUser.id || currentUser.is_admin)

  // The hover tooltip is pointer-only (it can't open on keyboard focus, since its
  // reference sits inside the button), so the decided summary also rides on
  // aria-label to stay reachable for keyboard/screen-reader users.
  const decidedByViewer = !!currentUser && decidedBy?.id === currentUser.id
  const decidedAttribution = decidedByViewer
    ? "You decided"
    : decidedBy
      ? `Decided by ${decidedBy.display_name}`
      : "Decided"
  const decidedSummary = `${decidedAttribution} at ${formatDateTime(decision.decided_at, "short_month_day_year_time")}`

  const pillBody = (
    <>
      {/* Tooltip wraps only the icon+label, not the avatar — UserAvatar carries
          its own hover card, and wrapping the whole pill would fire both
          popovers when hovering the avatar. */}
      <Tooltip content={decidedSummary} className="inline-flex items-center gap-1">
        <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
          alt_route
        </span>
        <span className="font-semibold">Decision</span>
      </Tooltip>
      {decidedBy && <UserAvatar user={decidedBy} size="xs" />}
    </>
  )

  // A viewer who can't undecide gets a static badge, not a button that focuses
  // and announces as actionable but does nothing on Enter/Space. Hold off on the
  // inert cursor until the user has loaded — otherwise the decider sees a
  // disabled-looking pill for the duration of the fetch.
  if (!canUndecide) {
    return (
      <span
        className={`btn btn-sm btn-decision btn-static select-none @mobile:min-h-8 ${isUserLoaded ? "cursor-default" : ""} ${className ?? ""}`}
        aria-label={decidedSummary}
      >
        {pillBody}
      </span>
    )
  }

  return (
    <button
      type="button"
      className={`btn btn-sm btn-decision select-none @mobile:min-h-8 ${className ?? ""}`}
      aria-label={`${decidedSummary}. Click to undo this decision.`}
      onClick={onToggle}
    >
      {pillBody}
    </button>
  )
}
