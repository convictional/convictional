import { useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useRef, useState } from "react"

import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useHotkeyInstall } from "~/react/shared/hooks/useHotkeyInstall"
import { isVisibleViewRow } from "~/react/shared/queries/mailboxViewEntries"
import { calendarAuthUrl, gmailAuthUrl } from "~/react/shared/urls"

import { EntryList } from "./components/EntryList"
import { EntryListSkeleton } from "./components/EntryListSkeleton"
import { Header } from "./components/Header"
import { HelpDialog } from "./components/HelpDialog"
import { InboxSetupBanner } from "./components/InboxSetupBanner"
import { MailboxViewBanner } from "./components/MailboxViewBanner"
import { MailboxViewCoverageNotice } from "./components/MailboxViewCoverageNotice"
import { MailboxViewError } from "./components/MailboxViewError"
import { MailboxViewLoading } from "./components/MailboxViewLoading"
import { MailboxViewSections } from "./components/MailboxViewSections"
import { OnboardingFocus } from "./components/OnboardingFocus"
import { UndoToast } from "./components/UndoToast"
import { WelcomeShow } from "./components/WelcomeShow"
import { entryTargetWithReturnTo } from "./entryTarget"
import { useInboxProgress } from "./hooks/useInboxProgress"
import { useMailboxEntries } from "./hooks/useMailboxEntries"
import { useMailboxHotkeys } from "./hooks/useMailboxHotkeys"
import { useMailboxView } from "./hooks/useMailboxView"
import type { ActiveMailboxView, MailboxEntry, MailboxSort, MailboxView } from "./types"

const UNDO_TIMEOUT_MS = 8000

// The client-rendered onboarding focus. It's a real focus template name (so
// ?mailbox_view_template=getting_started routes to it and the server persists it in
// the focus-preference cookie), but it has no server view — MailboxIndex renders
// OnboardingFocus for it instead of fetching entries.
// Mirrors GETTING_STARTED_TEMPLATE in app/helpers/mailbox_focus.py — keep the two in sync.
const GETTING_STARTED_TEMPLATE = "getting_started"

const ONBOARDING_VIEW: ActiveMailboxView = {
  kind: "template",
  id: `template:${GETTING_STARTED_TEMPLATE}`,
  title: "Getting started",
  view_request: null,
  channel_id: `template:${GETTING_STARTED_TEMPLATE}`,
  requires_goals: false,
  layout: "grouped",
}

export interface MailboxIndexProps {
  // Which server view to read. A route constant — the seven inbox paths are one
  // page — so it changes only by navigating, never within a route.
  view: MailboxView
  // The focus selector, straight off the route's search params. Not "initial":
  // under client routing the URL changes without remounting the island, so these
  // are live values that must not be frozen into state.
  sort?: MailboxSort
  mailbox_view_id?: string | null
  mailbox_view_template?: string | null
  goal_id?: string | null
}

interface UndoableAction {
  type: "archive" | "snooze"
  entryId: string
  // Snapshot of the snooze target, so the toast can confirm "Snoozed until …".
  snoozedUntil?: string
}

export function MailboxIndex({
  view,
  sort: sortParam,
  mailbox_view_id: mailboxViewId = null,
  mailbox_view_template: mailboxViewTemplate = null,
  goal_id: mailboxViewGoalId = null,
}: MailboxIndexProps) {
  // user_id forms the mailbox_sync / mailbox_view / inbox_progress topic identity. It
  // rides the current-user bootstrap (no per-response field), so all three subscriptions
  // gate on it being present.
  const { user } = useCurrentUser()
  const userId = user?.id ?? null
  const isSuperuser = user?.is_superuser ?? false

  const navigate = useNavigate()
  const inboxProgress = useInboxProgress(userId)
  // Sort comes from the route, not from the search object: only "/" declares the
  // param, but an undeclared param still reaches every match at runtime, so reading
  // it unconditionally would make "/unread?sort=oldest" meaningful — which no server
  // handler ever did.
  const sort: MailboxSort = view === "inbox" ? (sortParam ?? "newest") : "newest"

  // The Welcome getting-started entry: opening it takes over the island with a show
  // (its own sticky header), so its state lives here. Archive/snooze dismiss until reload.
  const [welcomeOpen, setWelcomeOpen] = useState(false)
  const [welcomeSkipped, setWelcomeSkipped] = useState(false)
  const [welcomeRead, setWelcomeRead] = useState(false)

  // Onboarding "Getting started" focus — client-rendered, no backing entries. It's a
  // real cookie-persisted focus: the server routes/persists it and the native "Clear
  // focus" control exits it, so there's no bespoke skip/dismiss here.
  // Onboarding is a Google-integration flow (connect Gmail + Calendar), so it only applies to users
  // who can connect them. Microsoft users can't, so it's "complete" (never offered) for them; Google
  // users keep the focus offered until both are connected.
  const supportsGoogle = inboxProgress.is_google_authenticated
  const gmailConnected = inboxProgress.has_gmail_integration && supportsGoogle
  const calendarConnected = inboxProgress.has_calendar_integration
  const onboardingComplete = !supportsGoogle || (gmailConnected && calendarConnected)
  const onboardingActive = mailboxViewTemplate === GETTING_STARTED_TEMPLATE

  // Stamp the URL the user is on so connecting Gmail returns them to their current
  // focus (e.g. /?mailbox_view_template=urgent_important), not bare "/" as a static
  // return_to would. Read at render — the island re-renders on every navigation.
  const gmailConnectUrl = gmailAuthUrl(window.location.pathname + window.location.search)

  const mailboxView = useMailboxView({
    initialViewId: mailboxViewId,
    // getting_started is client-rendered; never ask the server to generate a view for it.
    initialTemplate: onboardingActive ? null : mailboxViewTemplate,
    initialGoalId: mailboxViewGoalId,
    userId,
  })
  const isViewActive = mailboxView.active !== null && !mailboxView.isNotFound
  const isRanked = isViewActive && mailboxView.active?.layout === "ranked"

  // In view mode, hotkey navigation runs over the flat list of section entries.
  // Skip the inbox entry fetch when a view is active to avoid wasted requests
  // and keep the live channel narrowly scoped to the view, but only when the
  // server has finished telling us a view IS active — otherwise the initial
  // moments before /api/mailbox_views resolves would render an empty inbox.
  const skipInboxFetch = mailboxViewId !== null || mailboxViewTemplate !== null
  const entries = useMailboxEntries(userId, view, sort, { enabled: !skipInboxFetch })
  const { visibleEntries, loading, loadingMore, hasMore, hasLoadedMore, loadMore, resetToFirstPage } = entries
  // In view mode the visible rows come from mailboxView.entriesById, so route
  // mutations through that store; otherwise use the inbox-list store.
  const mutations = isViewActive ? mailboxView.mutations : entries.mutations

  // Must stay exactly the set MailboxViewSections renders, or hotkeys select rows that aren't on screen.
  const viewEntries = isViewActive
    ? mailboxView.sections.flatMap(section =>
        section.mailbox_entry_ids.map(id => mailboxView.entriesById[id]).filter(isVisibleViewRow)
      )
    : []
  const activeEntries = isViewActive ? viewEntries : visibleEntries

  // Load-time counts, deliberately not refreshed: taken before any archiving, they still describe what
  // a regeneration would newly reach. Only ever a trigger — archiving elsewhere can drain it unseen.
  const uncoveredEntryCount = (mailboxView.eligibleEntryCount ?? 0) - (mailboxView.consideredEntryCount ?? 0)
  const hotkeys = useMailboxHotkeys({ entries: activeEntries })

  const [helpOpen, setHelpOpen] = useState(false)
  const [undoable, setUndoable] = useState<UndoableAction | null>(null)
  const [snoozeOpenEntryId, setSnoozeOpenEntryId] = useState<string | null>(null)
  const undoTimerRef = useRef<number | null>(null)

  const containerRef = useRef<HTMLDivElement>(null)
  useHotkeyInstall(containerRef, snoozeOpenEntryId === null)

  const clearUndoTimer = useCallback(() => {
    if (undoTimerRef.current !== null) {
      clearTimeout(undoTimerRef.current)
      undoTimerRef.current = null
    }
  }, [])

  const scheduleUndo = useCallback(
    (action: UndoableAction) => {
      clearUndoTimer()
      setUndoable(action)
      undoTimerRef.current = window.setTimeout(() => {
        setUndoable(null)
        undoTimerRef.current = null
      }, UNDO_TIMEOUT_MS)
    },
    [clearUndoTimer]
  )

  useEffect(() => () => clearUndoTimer(), [clearUndoTimer])

  const handleArchiveWithUndo = useCallback(
    async (entry: MailboxEntry) => {
      try {
        await mutations.archive(entry.id)
        scheduleUndo({ type: "archive", entryId: entry.id })
      } catch {
        // mutation already showed flash and rolled back optimistic state
      }
    },
    [mutations, scheduleUndo]
  )

  const handleSnoozeWithUndo = useCallback(
    async (entry: MailboxEntry, snoozedUntil: string) => {
      try {
        await mutations.snooze(entry.id, snoozedUntil)
        scheduleUndo({ type: "snooze", entryId: entry.id, snoozedUntil })
      } catch {
        // mutation already showed flash and rolled back optimistic state
      }
    },
    [mutations, scheduleUndo]
  )

  const handleUndo = useCallback(async () => {
    if (!undoable) return
    const { type, entryId } = undoable
    clearUndoTimer()
    setUndoable(null)
    if (type === "archive") {
      await mutations.unarchive(entryId).catch(() => {})
    } else {
      await mutations.unsnooze(entryId).catch(() => {})
    }
  }, [undoable, mutations, clearUndoTimer])

  // Hotkey actions
  const onHotkeyArrowDown = useCallback(() => hotkeys.selectNext(), [hotkeys])
  const onHotkeyArrowUp = useCallback(() => hotkeys.selectPrevious(), [hotkeys])
  const onHotkeyEnter = useCallback(() => {
    const entry = hotkeys.selectedEntry()
    const target = entry && entryTargetWithReturnTo(entry.href)
    if (target) void navigate({ to: target.to, search: target.search })
  }, [hotkeys, navigate])
  const onHotkeyArchive = useCallback(() => {
    const entry = hotkeys.selectedEntry()
    if (!entry) return
    if (entry.is_archived) {
      mutations.unarchive(entry.id).catch(() => {})
    } else {
      handleArchiveWithUndo(entry)
    }
  }, [hotkeys, mutations, handleArchiveWithUndo])
  const onHotkeyMarkReadUnread = useCallback(() => {
    const entry = hotkeys.selectedEntry()
    if (!entry) return
    if (entry.is_unread) {
      mutations.markRead(entry.id).catch(() => {})
    } else {
      mutations.markUnread(entry.id).catch(() => {})
    }
  }, [hotkeys, mutations])
  const onHotkeySnooze = useCallback(() => {
    const entry = hotkeys.selectedEntry()
    if (!entry || entry.is_snoozed) return
    setSnoozeOpenEntryId(entry.id)
  }, [hotkeys])
  const onHotkeyHelp = useCallback(() => setHelpOpen(open => !open), [])
  const onHotkeyUndo = useCallback(() => {
    handleUndo()
  }, [handleUndo])

  const handleSnoozeOpenChange = useCallback((entryId: string, open: boolean) => {
    setSnoozeOpenEntryId(prev => {
      if (open) return entryId
      return prev === entryId ? null : prev
    })
  }, [])

  const handleRefresh = useCallback(() => {
    // Both saved views and built-in template sorts show the banner; refresh by the active view's
    // opaque id (a UUID for saved views, `template:<name>[:<goalId>]` for templates).
    if (!mailboxView.active) return
    mailboxView.refreshView(mailboxView.active.id)
  }, [mailboxView])

  const renderBody = () => {
    if (onboardingActive) {
      return (
        <OnboardingFocus
          gmailConnected={gmailConnected}
          gmailAuthUrl={gmailConnectUrl}
          calendarConnected={calendarConnected}
          calendarAuthUrl={calendarAuthUrl}
          welcomeSkipped={welcomeSkipped}
          welcomeRead={welcomeRead}
          onOpenWelcome={() => {
            // Opening the row marks it read, like opening any mailbox entry.
            setWelcomeOpen(true)
            setWelcomeRead(true)
          }}
          onArchiveWelcome={() => setWelcomeSkipped(true)}
          onSnoozeWelcome={() => setWelcomeSkipped(true)}
          onToggleWelcomeRead={() => setWelcomeRead(prev => !prev)}
        />
      )
    }
    // While a mailbox view is resolving (initial load, switch, or refresh) show the
    // skeleton loader — we don't yet know whether results are cached or generating,
    // and the skeleton is appropriate for both cases. If the response indicates active
    // generation, MailboxViewLoading takes over below the rendered sections (gated on
    // isGenerating). Checked before the inbox branch so the window before
    // mailboxView.active is set doesn't fall through to EntryList and flash its empty
    // state ("Inbox zero") when navigating into a custom view or changing its sort.
    if (mailboxView.loading) return <EntryListSkeleton />
    if (isViewActive) {
      if (mailboxView.errorMessage) return <MailboxViewError message={mailboxView.errorMessage} />
      if (mailboxView.active?.requires_goals && !mailboxView.hasGoalsForView) {
        return <MailboxViewError message="Create a goal first, then come back to see your inbox organized by goals." />
      }
      return (
        <>
          <MailboxViewCoverageNotice
            considered={mailboxView.consideredEntryCount}
            eligible={mailboxView.eligibleEntryCount}
          />
          <MailboxViewSections
            sections={mailboxView.sections}
            entriesById={mailboxView.entriesById}
            mutations={mutations}
            isRanked={isRanked}
            hasMoreEntries={mailboxView.hasMoreEntries}
            loadingMoreEntries={mailboxView.loadingMoreEntries}
            onLoadMoreEntries={mailboxView.loadMoreEntries}
            selectedId={hotkeys.selectedId}
            onSelect={id => {
              const idx = activeEntries.findIndex(e => e.id === id)
              if (idx >= 0) hotkeys.selectIndex(idx)
            }}
            onArchiveWithUndo={handleArchiveWithUndo}
            onSnoozeWithUndo={handleSnoozeWithUndo}
            snoozeOpenEntryId={snoozeOpenEntryId}
            onSnoozeOpenChange={handleSnoozeOpenChange}
            timezone={user?.time_zone ?? null}
          />
          {mailboxView.isGenerating && <MailboxViewLoading />}
        </>
      )
    }

    return (
      <EntryList
        entries={visibleEntries}
        view={view}
        selectedId={hotkeys.selectedId}
        hasMore={hasMore}
        hasLoadedMore={hasLoadedMore}
        loading={loading}
        loadingMore={loadingMore}
        onLoadMore={loadMore}
        onReturnToTop={resetToFirstPage}
        onSelect={id => {
          const idx = visibleEntries.findIndex(e => e.id === id)
          if (idx >= 0) hotkeys.selectIndex(idx)
        }}
        mutations={mutations}
        onArchiveWithUndo={handleArchiveWithUndo}
        onSnoozeWithUndo={handleSnoozeWithUndo}
        snoozeOpenEntryId={snoozeOpenEntryId}
        onSnoozeOpenChange={handleSnoozeOpenChange}
        timezone={user?.time_zone ?? null}
      />
    )
  }

  // Opening Welcome takes over the whole island: its show carries its own sticky
  // action header, so the mailbox header/banners step aside like a real show page.
  if (onboardingActive && welcomeOpen && !welcomeSkipped) {
    return (
      <div>
        <WelcomeShow
          read={welcomeRead}
          onToggleRead={() => setWelcomeRead(prev => !prev)}
          onBack={() => setWelcomeOpen(false)}
          onArchive={() => {
            setWelcomeSkipped(true)
            setWelcomeOpen(false)
          }}
          onSnooze={() => {
            setWelcomeSkipped(true)
            setWelcomeOpen(false)
          }}
        />
      </div>
    )
  }

  return (
    <div ref={containerRef}>
      <Header
        view={view}
        sort={sort}
        allViews={mailboxView.allViews}
        hasGoalsForView={mailboxView.hasGoalsForView}
        isSuperuser={isSuperuser}
        active={onboardingActive ? ONBOARDING_VIEW : isViewActive ? mailboxView.active : null}
        onboardingAvailable={!onboardingComplete}
        emailConnected={gmailConnected}
        createView={mailboxView.createView}
        updateView={mailboxView.updateView}
        deleteView={mailboxView.deleteView}
      />
      {!onboardingActive && <InboxSetupBanner state={inboxProgress} gmailAuthUrl={gmailConnectUrl} />}
      {isViewActive && mailboxView.active && (
        <MailboxViewBanner
          newMessagesCount={mailboxView.newMessagesCount}
          uncoveredCount={uncoveredEntryCount}
          cleared={mailboxView.isCleared}
          onRefresh={handleRefresh}
        />
      )}
      <div id="mailbox-entries-container" className="px-2">
        {renderBody()}
      </div>
      <div className="hidden">
        <button data-hotkey="ArrowUp" onClick={onHotkeyArrowUp} type="button" />
        <button data-hotkey="ArrowDown" onClick={onHotkeyArrowDown} type="button" />
        <button data-hotkey="Enter" onClick={onHotkeyEnter} type="button" />
        <button data-hotkey="e" onClick={onHotkeyArchive} type="button" />
        <button data-hotkey="r" onClick={onHotkeyMarkReadUnread} type="button" />
        <button data-hotkey="b" onClick={onHotkeySnooze} type="button" />
        <button data-hotkey="Shift+?" onClick={onHotkeyHelp} type="button" />
        <button data-hotkey="Meta+z,Control+z" onClick={onHotkeyUndo} type="button" />
      </div>
      {/* Keying on the entry id remounts the toast on each new archive/snooze, restarting the 8s countdown fill from 0. */}
      <UndoToast
        key={undoable?.entryId ?? "none"}
        action={undoable?.type ?? null}
        snoozedUntil={undoable?.snoozedUntil}
        timezone={user?.time_zone ?? null}
        onUndo={handleUndo}
      />
      <HelpDialog isOpen={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  )
}
