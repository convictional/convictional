import { useBoundaryNavigate } from "~/react/shared/hooks/useBoundaryNavigate"
import { Tooltip } from "~/react/ui/Tooltip"

import { MailboxSegmentButton } from "./MailboxSegmentButton"
import { MAILBOX_ACTION_CLUSTER_CLASS, MAILBOX_ACTION_DIVIDER_CLASS } from "./segments"
import type { MailboxEntryPositionLabel } from "./useMailboxEntryNavigation"

interface MailboxEntryNavProps {
  prevHref: string | null
  nextHref: string | null
  loadingNext: boolean
  generating: boolean
  positionLabel: MailboxEntryPositionLabel | null
}

// The label between the arrows names where you are — the section title (grouped view)
// or the sort's name (ranked custom sort). The exact "N of M" is disclosed on hover
// rather than shown inline (the whole pill's fill already conveys progress), keeping
// the chip compact. Falls back to the bare count when there's no name.
function PositionLabel({ name, position, total }: MailboxEntryPositionLabel) {
  const count = `${position} of ${total}`
  const tooltip = name ? `${name} · ${count}` : count
  return (
    <Tooltip content={tooltip} placement="bottom">
      <span
        aria-label={tooltip}
        className="block min-w-[6rem] max-w-[12rem] truncate px-2 text-center text-xs text-base-600"
      >
        {name ?? count}
      </span>
    </Tooltip>
  )
}

// Progress through the section/sort, filled left-to-right across the entire pill so
// prev arrow, label, and next arrow all sit over it. Painted behind the controls
// (-z-10 within the cluster's isolated stacking context) so it reads as a track, not
// a button state.
function positionFillPercent(positionLabel: MailboxEntryPositionLabel | null, generating: boolean): number | null {
  if (generating || positionLabel === null || positionLabel.total <= 0) return null
  return Math.min(100, Math.round((positionLabel.position / positionLabel.total) * 100))
}

// Prev/next arrows for walking the mailbox list the entry was opened from. The
// navigation is resolved by MailboxActionBar (which owns the hook, so the archive
// action can advance to the same next entry) and passed in here. ArrowLeft/ArrowRight
// drive the same navigation as the buttons — horizontal so they don't fight page scroll.
// A focus-mode view/sort names the current section/sort between the arrows, with the
// whole pill filled to the position within it (and "Organizing…" with disabled arrows
// while it's still being generated).
export function MailboxEntryNav({ prevHref, nextHref, loadingNext, generating, positionLabel }: MailboxEntryNavProps) {
  // A neighbor may be a client-routed page (another chat) or a legacy one — let
  // the boundary-aware navigate pick client vs full-document per target.
  const navigate = useBoundaryNavigate()
  const fillPercent = positionFillPercent(positionLabel, generating)
  return (
    <div className={`${MAILBOX_ACTION_CLUSTER_CLASS} relative isolate overflow-hidden`}>
      {fillPercent !== null && (
        <span
          aria-hidden
          className="absolute inset-y-0 left-0 -z-10 bg-base-300"
          style={{ width: `${fillPercent}%` }}
        />
      )}
      <MailboxSegmentButton
        icon="chevron_left"
        label="Previous"
        hotkey="ArrowLeft"
        disabled={generating || prevHref === null}
        onClick={() => {
          if (prevHref) navigate(prevHref)
        }}
      />
      {generating ? (
        <span className="min-w-[6rem] px-2 text-center text-xs text-base-600">Organizing…</span>
      ) : positionLabel !== null ? (
        <PositionLabel {...positionLabel} />
      ) : (
        <span className={MAILBOX_ACTION_DIVIDER_CLASS} />
      )}
      <MailboxSegmentButton
        icon="chevron_right"
        label="Next"
        hotkey="ArrowRight"
        disabled={generating || nextHref === null}
        loading={loadingNext || generating}
        onClick={() => {
          if (nextHref) navigate(nextHref)
        }}
      />
    </div>
  )
}
