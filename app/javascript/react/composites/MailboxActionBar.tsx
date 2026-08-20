import { useCallback, useEffect, useRef, useState } from "react"
import type { ReactNode } from "react"

import { BackButton } from "~/react/composites/BackButton"
import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { useAutoMarkRead } from "~/react/shared/hooks/useAutoMarkRead"
import { useBoundaryNavigate } from "~/react/shared/hooks/useBoundaryNavigate"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useHotkeyInstall } from "~/react/shared/hooks/useHotkeyInstall"
import { formatSnoozedUntil } from "~/react/ui/DateTime"
import { Tooltip } from "~/react/ui/Tooltip"
import { queueFlash, showFlash } from "~/shared/flash"

import { MailboxEntryNav } from "./MailboxActionBar/MailboxEntryNav"
import { MailboxSegmentButton } from "./MailboxActionBar/MailboxSegmentButton"
import {
  MAILBOX_ACTION_CLUSTER_CLASS,
  MAILBOX_ACTION_DIVIDER_CLASS,
  MAILBOX_ACTION_SEGMENT_CLASS,
} from "./MailboxActionBar/segments"
import { SnoozeDropdown } from "./MailboxActionBar/SnoozeDropdown"
import { type MailboxEntryNavigation, useMailboxEntryNavigation } from "./MailboxActionBar/useMailboxEntryNavigation"

// Re-exported so consumers that inject a `leftSlot` button (e.g. the email thread
// AI toggle) can match the segment styling instead of rendering a standalone pill.
export { MAILBOX_ACTION_SEGMENT_CLASS }

export interface MailboxActionUrls {
  archive: string
  unarchive: string
  markRead: string
  markUnread: string
  snooze: string
  unsnooze: string
}

// The generic, resource-agnostic mailbox-entry action API, keyed by entry id —
// every surface that renders a MailboxActionBar drives its triage actions
// through these endpoints.
export function mailboxActionUrls(mailboxEntryId: string): MailboxActionUrls {
  const base = `/api/mailbox_entries/${mailboxEntryId}`
  return {
    archive: `${base}/archive`,
    unarchive: `${base}/unarchive`,
    markRead: `${base}/mark_read`,
    markUnread: `${base}/mark_unread`,
    snooze: `${base}/snooze`,
    unsnooze: `${base}/unsnooze`,
  }
}

export interface MailboxState {
  isUnread: boolean
  isArchived: boolean
  isSnoozed: boolean
  snoozedUntil: string | null
}

interface MailboxActionBarProps {
  state: MailboxState
  actionUrls: MailboxActionUrls
  back: { label: string; url: string }
  // The mailbox entry this show page renders. When the entry was opened from a
  // navigable main-mailbox list, prev/next arrows appear next to the back button
  // (MailboxEntryNav renders nothing otherwise).
  mailboxEntryId?: string
  // A pre-built navigation object shared with the host (the email thread show lifts
  // the hook so its reply composer can advance to the same next entry the arrows
  // point at). When provided, the internal hook no-ops and this drives the arrows.
  navigation?: MailboxEntryNavigation
  leftSlot?: ReactNode
  // Right-justified at the far end of the toolbar (ml-auto pushes it past the
  // action cluster).
  trailingSlot?: ReactNode
  onStateChange?: (next: MailboxState) => void
  // Snooze isn't meaningful for every resource (e.g. chat notifications).
  showSnooze?: boolean
  // Render the back link as a NavLink so it client-routes when `back.url` is a
  // registered SPA path; a plain <a> (the default) full-document navigates. The
  // email thread passes this so a `return_to` pointing at an SPA index stays a
  // soft nav; the inbox default (`/`) hard-navs either way.
  navLink?: boolean
}

function dispatchThreadEvent(name: "thread-marked-read" | "thread-marked-unread"): void {
  window.dispatchEvent(new CustomEvent(name))
}

export function MailboxActionBar({
  state,
  actionUrls,
  back,
  mailboxEntryId,
  navigation,
  leftSlot,
  trailingSlot,
  onStateChange,
  showSnooze = true,
  navLink = false,
}: MailboxActionBarProps) {
  const [localState, setLocalState] = useState<MailboxState>(state)
  const [snoozeOpen, setSnoozeOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const autoMarkRef = useRef<HTMLSpanElement>(null)
  const { user } = useCurrentUser()
  const timezone = user?.time_zone ?? null
  // Advancing to the next entry may land on a client-routed page (another chat) or
  // a legacy one; the boundary-aware navigate keeps SPA hops client-side.
  const navigate = useBoundaryNavigate()

  // Sync local state if the parent pushes a new `state` prop (e.g. from a WebSocket
  // update). Without this, optimistic local updates would silently override the
  // authoritative parent state on re-render.
  useEffect(() => {
    setLocalState(state)
  }, [state])

  // Disable hotkey installation while the snooze popover is open so `e`/`u`/`b`
  // dismiss the popover via floating-ui's keyboard handling instead of triggering
  // archive/back/snooze actions.
  useHotkeyInstall(containerRef, !snoozeOpen)

  // Owned here (not in MailboxEntryNav) so archiving can advance to the same next
  // entry the arrow points at. "" when this bar has no entry — the hook no-ops.
  // A host that lifted the hook (the email thread show, so its reply composer
  // shares one navigation) passes `navigation` in; the internal hook then no-ops
  // (mailboxEntryId "") so we don't double-subscribe to the focus-mode channel.
  const internalNav = useMailboxEntryNavigation({ mailboxEntryId: navigation ? "" : (mailboxEntryId ?? "") })
  const nav = navigation ?? internalNav

  const updateState = useCallback(
    (next: MailboxState) => {
      setLocalState(next)
      onStateChange?.(next)
    },
    [onStateChange]
  )

  useAutoMarkRead({
    ref: autoMarkRef,
    enabled: localState.isUnread,
    url: actionUrls.markRead,
    onMarkedRead: useCallback(() => {
      setLocalState(prev => {
        const next = { ...prev, isUnread: false }
        onStateChange?.(next)
        return next
      })
    }, [onStateChange]),
  })

  const post = useCallback(async (url: string, body?: unknown) => {
    const init: RequestInit = { method: "POST" }
    if (body !== undefined) init.body = JSON.stringify(body)
    await apiFetch(url, init)
  }, [])

  async function handleArchive() {
    try {
      await post(actionUrls.archive)
      // Resolve the next entry's href (hydrating a not-yet-loaded focus neighbor when needed) from
      // the pre-archive order, then drop this entry from the navigable cache so it's gone from the
      // walk (and the list on back-navigation) before we advance.
      const target = (await nav.resolveNextHref()) ?? back.url
      nav.markCurrentArchived()
      // Advance to the next entry when there is one; otherwise the originating
      // mailbox. nextHref carries the list's return_to, so the arrows keep working.
      navigate(target)
    } catch {
      showFlash("Couldn't archive.")
    }
  }

  async function handleUnarchive() {
    try {
      await post(actionUrls.unarchive)
      updateState({ ...localState, isArchived: false })
    } catch {
      showFlash("Couldn't unarchive.")
    }
  }

  async function handleMarkRead() {
    const previous = localState
    updateState({ ...localState, isUnread: false })
    try {
      await post(actionUrls.markRead)
      dispatchThreadEvent("thread-marked-read")
    } catch {
      updateState(previous)
      showFlash("Couldn't mark as read.")
    }
  }

  async function handleMarkUnread() {
    try {
      await post(actionUrls.markUnread)
      dispatchThreadEvent("thread-marked-unread")
      navigate(back.url)
    } catch {
      showFlash("Couldn't mark as unread.")
    }
  }

  async function handleSnooze(snoozedUntil: string) {
    try {
      await post(actionUrls.snooze, { snoozed_until: snoozedUntil })
      // Advance to the next entry like archive does: resolve the next href from the pre-snooze
      // order (hydrating a not-yet-loaded focus neighbor when needed), drop this entry from the
      // walk, then navigate. Falls back to the originating mailbox when there's no next entry.
      const target = (await nav.resolveNextHref()) ?? back.url
      nav.markCurrentSnoozed(snoozedUntil)
      // The redirect tears down this island, so queue the confirmation to fire
      // on the destination shell mount rather than showing an in-page flash.
      queueFlash(formatSnoozedUntil(snoozedUntil, timezone), "success")
      navigate(target)
    } catch (err) {
      if (err instanceof ApiError && err.status === 501) {
        showFlash("Snoozing is not yet supported here.")
      } else {
        showFlash("Couldn't snooze.")
      }
    }
  }

  async function handleUnsnooze() {
    try {
      await post(actionUrls.unsnooze)
      updateState({ ...localState, isSnoozed: false, snoozedUntil: null })
    } catch {
      showFlash("Couldn't unsnooze.")
    }
  }

  return (
    <div ref={containerRef} className="flex items-center gap-2 w-full">
      {/* Back and archive stay standalone pills — only the actions below are joined. */}
      <BackButton back={back} iconOnly navLink={navLink} hotkeyEnabled={!snoozeOpen} />

      {nav.visible && (
        // Hidden on mobile: the prev/next cluster overflows the narrow toolbar.
        <div className="hidden sm:flex">
          <MailboxEntryNav
            prevHref={nav.prevHref}
            nextHref={nav.nextHref}
            loadingNext={nav.loadingNext}
            generating={nav.generating}
            positionLabel={nav.positionLabel}
          />
        </div>
      )}

      {localState.isArchived ? (
        <Tooltip content="Unarchive" placement="bottom">
          <button type="button" onClick={handleUnarchive} aria-label="Unarchive" className="btn btn-square">
            <span className="material-symbols-outlined text-lg">unarchive</span>
          </button>
        </Tooltip>
      ) : (
        <Tooltip content="Archive" placement="bottom">
          <button
            type="button"
            onClick={handleArchive}
            aria-label="Archive"
            className="btn btn-square"
            data-hotkey="e"
          >
            <span className="material-symbols-outlined text-lg">archive</span>
          </button>
        </Tooltip>
      )}

      <div className={MAILBOX_ACTION_CLUSTER_CLASS}>
        {localState.isUnread ? (
          <MailboxSegmentButton icon="drafts" label="Mark read" onClick={handleMarkRead} />
        ) : (
          <MailboxSegmentButton icon="mark_email_unread" label="Mark unread" onClick={handleMarkUnread} />
        )}

        {showSnooze && (
          <>
            <span className={MAILBOX_ACTION_DIVIDER_CLASS} />

            {localState.isSnoozed ? (
              <MailboxSegmentButton
                icon="alarm_off"
                label="Unsnooze"
                tooltip={formatSnoozedUntil(localState.snoozedUntil, timezone)}
                onClick={handleUnsnooze}
                className="text-primary"
                iconClassName="text-xl"
              />
            ) : (
              <SnoozeDropdown
                isOpen={snoozeOpen}
                onOpenChange={setSnoozeOpen}
                onSnooze={handleSnooze}
                timezone={timezone}
                buttonClassName={MAILBOX_ACTION_SEGMENT_CLASS}
              />
            )}
          </>
        )}

        {leftSlot && (
          <>
            <span className={MAILBOX_ACTION_DIVIDER_CLASS} />
            {leftSlot}
          </>
        )}
      </div>
      {trailingSlot && <div className="ml-auto min-w-0 flex items-center gap-3">{trailingSlot}</div>}
      <span ref={autoMarkRef} aria-hidden="true" className="sr-only" />
    </div>
  )
}
