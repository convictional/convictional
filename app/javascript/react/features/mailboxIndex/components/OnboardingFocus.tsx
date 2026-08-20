import { useState } from "react"

import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { connectCalendarWithPreference } from "~/react/shared/recall_ai/calendarConnect"
import { feedbackDialogStore } from "~/react/shared/stores/feedbackDialog"
import { GmailLogo } from "~/react/ui/GmailLogo"
import { GoogleCalendarLogo } from "~/react/ui/GoogleCalendarLogo"
import { McpServerLogo } from "~/react/ui/McpServerLogo"
import { Tooltip } from "~/react/ui/Tooltip"

const MCP_GUIDE_URL = "https://guides.convictional.com/integrations/mcp/#mcp-server"
const GUIDES_URL = "https://guides.convictional.com"

// Single-sourced so the desktop hover tooltip and the mobile inline microcopy stay identical.
const GMAIL_CONNECT_REASSURANCE =
  "Your emails are encrypted at rest, and attested to by SOC2 Type II and Google's CASA level 3. They can only be read by you."
const CALENDAR_CONNECT_REASSURANCE =
  "The Notetaker always asks to be admitted and can be denied from any meeting. Recordings stay private to you."

// A client-rendered "Getting started" focus. The items are styled as real mailbox
// rows (same width, indicator, avatar/title/preview anatomy as EntryRow) but have no
// backing entries — done-state is derived from real signals (Gmail connection) rather
// than stored, so there's no synthetic data to maintain. It's a normal focus: exiting
// is the header's "Clear focus" control, not a bespoke skip.
interface OnboardingFocusProps {
  gmailConnected: boolean
  gmailAuthUrl?: string
  calendarConnected: boolean
  calendarAuthUrl?: string
  // Welcome-row state lives in MailboxIndex, since opening it takes over the whole
  // island (its show has its own sticky header, replacing the list).
  welcomeSkipped: boolean
  welcomeRead: boolean
  onOpenWelcome: () => void
  onArchiveWelcome: () => void
  onSnoozeWelcome: () => void
  onToggleWelcomeRead: () => void
}

// The indicator + avatar + title/preview block shared by every getting-started row, so
// they line up byte-for-byte with each other (and read like real mailbox rows). `dimmed`
// is the read/done treatment; `showIndicator` hides the unread dot once a row is read.
function RowBody({
  icon,
  title,
  preview,
  showIndicator = true,
  dimmed = false,
  wrapPreview = false,
}: {
  icon: string
  title: string
  preview: string
  showIndicator?: boolean
  dimmed?: boolean
  wrapPreview?: boolean
}) {
  return (
    <div className="grid grid-cols-[auto_1fr] items-center gap-2 px-2 py-2.5 min-w-0">
      <div className="w-3 flex items-center justify-center">
        {showIndicator && <div className="w-1.5 h-1.5 rounded-full bg-info-content" />}
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-3">
          <div className={`shrink-0 ${dimmed ? "grayscale opacity-75" : ""}`}>
            <div className="w-8 h-8 rounded-full bg-base-300 flex items-center justify-center">
              <span className="material-symbols-outlined text-base-content/50">{icon}</span>
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <span
              className={`block truncate text-sm ${dimmed ? "font-medium text-base-600/70" : "font-semibold text-base-700"}`}
            >
              {title}
            </span>
            <p
              className={`mt-0.5 text-xs ${wrapPreview ? "" : "truncate"} ${dimmed ? "text-base-500" : "text-base-600"}`}
            >
              {preview}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// Whole row is an OAuth link; hover reveals Connect + a shield-tooltip reassurance.
// data-hx-boost="false" so the boosted AJAX layer doesn't intercept the cross-origin redirect.
function GmailSetupRow({ gmailAuthUrl }: { gmailAuthUrl: string }) {
  const isMobile = useIsMobile()
  // No hover on touch: the whole card is the connect link, with the action shown
  // inline and the encryption reassurance as plain microcopy (a tooltip is unreachable).
  if (isMobile) {
    return (
      <li className="thread-item">
        <div className="rounded-lg">
          <RowBody
            icon="mail"
            title="Connect your email"
            preview="Collapse email, chat, and handoffs into one place. Assign it, talk it over, pass on what isn't yours."
            wrapPreview
          />
          <div className="flex flex-col gap-2 px-3 pb-3">
            <a href={gmailAuthUrl} data-hx-boost="false" className="btn btn-primary w-full gap-1.5">
              <span className="w-5">
                <GmailLogo />
              </span>
              Connect Gmail
            </a>
            <span className="inline-flex items-start gap-1 text-xs text-base-500">
              <span className="material-symbols-outlined text-sm leading-none">shield</span>
              {GMAIL_CONNECT_REASSURANCE}
            </span>
          </div>
        </div>
      </li>
    )
  }
  return (
    <li className="thread-item">
      <div className="group relative grid grid-cols-[1fr_auto] overflow-hidden rounded-lg transition-all hover:bg-base-300">
        <a href={gmailAuthUrl} className="block min-w-0" data-hx-boost="false">
          <RowBody
            icon="mail"
            title="Connect your email"
            preview="Collapse email, chat, and handoffs into one place. Assign it, talk it over, pass on what isn't yours."
          />
        </a>
        <div className="hidden items-center gap-3 p-2 group-hover:flex">
          <Tooltip content={GMAIL_CONNECT_REASSURANCE}>
            <span className="material-symbols-outlined cursor-help text-base leading-none text-base-500">shield</span>
          </Tooltip>
          <a href={gmailAuthUrl} className="btn btn-primary flex items-center gap-1.5" data-hx-boost="false">
            <span className="w-6">
              <GmailLogo />
            </span>
            Connect Gmail
          </a>
        </div>
      </div>
    </li>
  )
}

// The calendar ask carries the notetaker auto-join preference the old onboarding stepper
// collected at connect time. It's a client choice appended to the connect URL on click
// (the server bakes in return_to but not the preference), so this row can't be a plain
// link like the others — it owns toggle state and builds the URL when connecting. The
// resting row is a one-liner like its siblings; hovering reveals the auto-join toggle and
// Connect in the same right-side action area real rows use, with the admission/privacy
// reassurance tucked into the lock icon's tooltip so it all fits on one line.
function CalendarSetupRow({ calendarAuthUrl }: { calendarAuthUrl: string }) {
  const [autoJoin, setAutoJoin] = useState(true)
  const connect = () => connectCalendarWithPreference(calendarAuthUrl, autoJoin)
  const isMobile = useIsMobile()

  // On touch the toggle and Connect can't hide behind hover; stack them inline
  // under the row, with the admission/privacy note as plain microcopy.
  if (isMobile) {
    return (
      <li className="thread-item">
        <div className="rounded-lg">
          <RowBody
            icon="calendar_month"
            title="Connect your calendar"
            preview="Recordings, transcripts, and decisions from every call, compounding in your company brain."
            wrapPreview
          />
          <div className="flex flex-col gap-2 px-3 pb-3">
            <label className="flex cursor-pointer items-center justify-between gap-3">
              <span className="text-sm text-base-700">Auto-join meetings</span>
              <input
                type="checkbox"
                className="toggle toggle-primary toggle-sm shrink-0"
                checked={autoJoin}
                onChange={event => setAutoJoin(event.target.checked)}
                aria-label="Auto-join meetings with the Notetaker"
              />
            </label>
            <button className="btn btn-primary w-full gap-1.5" onClick={connect}>
              <span className="w-4">
                <GoogleCalendarLogo />
              </span>
              Connect calendar
            </button>
            <span className="inline-flex items-start gap-1 text-xs text-base-500">
              <span className="material-symbols-outlined text-sm leading-none">lock</span>
              {CALENDAR_CONNECT_REASSURANCE}
            </span>
          </div>
        </div>
      </li>
    )
  }

  return (
    <li className="thread-item">
      <div className="group relative grid grid-cols-[1fr_auto] items-center overflow-hidden rounded-lg transition-all hover:bg-base-300">
        <RowBody
          icon="calendar_month"
          title="Connect your calendar"
          preview="Recordings, transcripts, and decisions from every call, compounding in your company brain."
        />
        <div className="hidden items-center gap-3 p-2 group-hover:flex">
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              className="toggle toggle-primary toggle-sm shrink-0"
              checked={autoJoin}
              onChange={event => setAutoJoin(event.target.checked)}
              aria-label="Auto-join meetings with the Notetaker"
            />
            <span className="whitespace-nowrap text-xs text-base-600">Auto-join meetings</span>
          </label>
          <Tooltip content={CALENDAR_CONNECT_REASSURANCE}>
            <span className="material-symbols-outlined cursor-help text-base leading-none text-base-500">lock</span>
          </Tooltip>
          <button className="btn btn-primary gap-1.5" onClick={connect}>
            <span className="w-4">
              <GoogleCalendarLogo />
            </span>
            Connect calendar
          </button>
        </div>
      </div>
    </li>
  )
}

// Clicking the row opens WelcomeShow (MailboxIndex takes over the island); the hover
// actions mirror a real mailbox row. State is the parent's so archive/read survive the
// open/close and the row and its show stay in sync.
interface WelcomeRowProps {
  read: boolean
  onOpen: () => void
  onArchive: () => void
  onSnooze: () => void
  onToggleRead: () => void
}

function WelcomeRow({ read, onOpen, onArchive, onSnooze, onToggleRead }: WelcomeRowProps) {
  const { user } = useCurrentUser()
  // Only mention the organization when the admin can actually name it (still unset).
  const canNameOrganization = (user?.is_admin ?? false) && !user?.organization_name?.trim()
  const preview = canNameOrganization
    ? "Customize your name, photo, and organization"
    : "Customize your name and photo"
  const isMobile = useIsMobile()
  // On touch the row just taps to open; archive/snooze/read live in the show's sticky
  // header, so the hover triage is desktop-only.
  if (isMobile) {
    return (
      <li className="thread-item">
        <button
          type="button"
          onClick={onOpen}
          className="grid w-full grid-cols-[1fr_auto] items-center rounded-lg text-left transition-colors active:bg-base-300"
        >
          <RowBody
            icon="person"
            title="Create your profile"
            preview={preview}
            showIndicator={!read}
            dimmed={read}
            wrapPreview
          />
          <span className="material-symbols-outlined pr-3 text-base-400">chevron_right</span>
        </button>
      </li>
    )
  }
  const iconClass = "material-symbols-outlined text-xl text-base-600 hover:text-base-800"
  const stop = (fn: () => void) => (event: React.MouseEvent) => {
    event.stopPropagation()
    fn()
  }
  return (
    <li className="thread-item">
      <div className="group relative grid grid-cols-[1fr_auto] items-center overflow-hidden rounded-lg transition-all hover:bg-base-300">
        <button type="button" onClick={onOpen} className="min-w-0 cursor-pointer text-left">
          <RowBody icon="person" title="Create your profile" preview={preview} showIndicator={!read} dimmed={read} />
        </button>
        <div className="hidden items-center gap-4 p-2 group-hover:flex">
          <Tooltip content="Archive">
            <button type="button" onClick={stop(onArchive)} aria-label="Archive" className="cursor-pointer">
              <span className={iconClass}>archive</span>
            </button>
          </Tooltip>
          <Tooltip content={read ? "Mark unread" : "Mark read"}>
            <button
              type="button"
              onClick={stop(onToggleRead)}
              aria-label={read ? "Mark unread" : "Mark read"}
              className="cursor-pointer"
            >
              <span className={iconClass}>{read ? "mark_email_unread" : "drafts"}</span>
            </button>
          </Tooltip>
          <Tooltip content="Snooze">
            <button type="button" onClick={stop(onSnooze)} aria-label="Snooze" className="cursor-pointer">
              <span className={iconClass}>snooze</span>
            </button>
          </Tooltip>
        </div>
      </div>
    </li>
  )
}

// A row of stylised resource links under the getting-started items: docs and a way to reach us.
// Not mailbox rows — they're always-there footers, so they sit below the list, not in it.
function ResourceLinks() {
  const linkClass = "inline-flex items-center gap-1.5 transition-colors hover:text-base-700"
  return (
    <div className="mt-3 mx-2 flex flex-wrap items-center gap-4 border-t border-base-200 px-2 pt-4 text-xs text-base-500">
      <a href={MCP_GUIDE_URL} target="_blank" rel="noopener noreferrer" data-hx-boost="false" className={linkClass}>
        <span className="h-3.5 w-3.5">
          <McpServerLogo />
        </span>
        MCP Docs
      </a>
      <span className="text-base-400" aria-hidden="true">
        ·
      </span>
      <a href={GUIDES_URL} target="_blank" rel="noopener noreferrer" data-hx-boost="false" className={linkClass}>
        <span className="material-symbols-outlined text-base leading-none">menu_book</span>
        Help Docs
      </a>
      <span className="text-base-400" aria-hidden="true">
        ·
      </span>
      <button
        type="button"
        onClick={() => feedbackDialogStore.getState().open()}
        className={`${linkClass} cursor-pointer`}
      >
        <span className="material-symbols-outlined text-base leading-none">feedback</span>
        Feedback
      </button>
    </div>
  )
}

export function OnboardingFocus({
  gmailConnected,
  gmailAuthUrl,
  calendarConnected,
  calendarAuthUrl,
  welcomeSkipped,
  welcomeRead,
  onOpenWelcome,
  onArchiveWelcome,
  onSnoozeWelcome,
  onToggleWelcomeRead,
}: OnboardingFocusProps) {
  return (
    <div id="mailbox-entries-live">
      <ul className="mailbox-entries-page">
        {!welcomeSkipped && (
          <WelcomeRow
            read={welcomeRead}
            onOpen={onOpenWelcome}
            onArchive={onArchiveWelcome}
            onSnooze={onSnoozeWelcome}
            onToggleRead={onToggleWelcomeRead}
          />
        )}
        {!gmailConnected && gmailAuthUrl && <GmailSetupRow gmailAuthUrl={gmailAuthUrl} />}
        {!calendarConnected && calendarAuthUrl && <CalendarSetupRow calendarAuthUrl={calendarAuthUrl} />}
      </ul>
      <ResourceLinks />
    </div>
  )
}
