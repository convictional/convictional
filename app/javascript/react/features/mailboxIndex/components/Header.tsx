import { Link, useNavigate } from "@tanstack/react-router"

import { apiFetch } from "~/react/shared/apiFetch"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { Dropdown } from "~/react/ui/Dropdown"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { Tooltip } from "~/react/ui/Tooltip"
import { showFlash } from "~/shared/flash"

import type { ActiveMailboxView, MailboxSort, MailboxView, MailboxViewLayout, MailboxViewSummary } from "../types"
import { FocusDropdown } from "./FocusDropdown"

interface NewEmailThreadResponse {
  thread_id: string
}

// Hook-driven rather than a module function: the new thread is a client route, so
// navigating to it needs the router.
function useStartNewThread() {
  const navigate = useNavigate()
  return async () => {
    try {
      const response = await apiFetch<NewEmailThreadResponse>("/api/email_threads", {
        method: "POST",
      })
      void navigate({ to: "/email_threads/$emailThreadId", params: { emailThreadId: response.thread_id } })
    } catch {
      showFlash("Couldn't start a new thread. Please try again.", "error")
    }
  }
}

const VIEW_LABELS: Record<MailboxView, string> = {
  inbox: "All",
  unread: "Unread",
  archived: "Archived",
  sent: "Sent",
  drafts: "Drafts",
  assigned_to_me: "Assigned to me",
  snoozed: "Snoozed",
}

const SORT_LABELS: Record<MailboxSort, string> = {
  newest: "Newest",
  oldest: "Oldest",
}

const VIEW_LINKS = [
  { view: "inbox", to: "/", hotkey: "g i" },
  { view: "unread", to: "/unread", hotkey: "g u" },
  { view: "assigned_to_me", to: "/assigned_to_me", hotkey: "g m" },
  { view: "snoozed", to: "/snoozed", hotkey: "g z" },
  { view: "sent", to: "/sent", hotkey: "g s" },
  { view: "drafts", to: "/drafts", hotkey: "g d" },
  { view: "archived", to: "/archived", hotkey: "g a" },
] as const satisfies readonly { view: MailboxView; to: string; hotkey: string }[]

interface HeaderProps {
  view: MailboxView
  sort: MailboxSort
  allViews: MailboxViewSummary[]
  hasGoalsForView: boolean
  isSuperuser: boolean
  active: ActiveMailboxView | null
  // Whether the onboarding "Getting started" focus should be offered in the Focus dropdown
  // (until Gmail and Calendar are both connected), so it's re-enterable after clearing.
  onboardingAvailable: boolean
  // Compose starts an email thread, which can't be sent without an email integration —
  // keep the button muted (not primary) until email is connected.
  emailConnected: boolean
  createView: (params: { view_request: string; title?: string; layout?: MailboxViewLayout }) => Promise<void>
  updateView: (
    viewId: string,
    params: { view_request?: string; title?: string; layout?: MailboxViewLayout }
  ) => Promise<void>
  deleteView: (viewId: string) => Promise<void>
}

function FilterDropdown({ view }: { view: MailboxView }) {
  return (
    <Dropdown
      placement="bottom-start"
      trigger={
        <button
          type="button"
          className="btn border border-neutral font-normal text-base-600 flex items-center gap-1"
          data-test-id="inbox-filter-dropdown"
        >
          {VIEW_LABELS[view]}
        </button>
      }
      className="dropdown-card p-2 z-50"
    >
      <ul>
        {VIEW_LINKS.map(link => (
          <li key={link.view} className="group">
            <Link className="dropdown-item relative text-xs" to={link.to} data-hotkey={link.hotkey}>
              <span>{VIEW_LABELS[link.view]}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Dropdown>
  )
}

// Plain inbox ordering only. Custom views and sorts (and the AI templates) now live in the
// neighboring Focus dropdown, so this control is purely Newest/Oldest.
function SortDropdown({ sort }: { sort: MailboxSort }) {
  return (
    <Dropdown
      placement="bottom-start"
      trigger={
        <button type="button" className="btn border border-neutral font-normal text-base-600 flex items-center gap-1">
          <span className="material-symbols-outlined text-lg">sort</span>
          {SORT_LABELS[sort]}
        </button>
      }
      className="dropdown-card z-50"
    >
      <ul className="p-2">
        <li>
          <Link
            className="dropdown-item text-xs flex items-center justify-between gap-4"
            to="/"
            search={{ sort: "newest" }}
          >
            <span>Newest</span>
          </Link>
        </li>
        <li>
          <Link
            className="dropdown-item text-xs flex items-center justify-between gap-4"
            to="/"
            search={{ sort: "oldest" }}
          >
            <span>Oldest</span>
          </Link>
        </li>
      </ul>
    </Dropdown>
  )
}

function ComposeButton({ emailConnected }: { emailConnected: boolean }) {
  const startNewThread = useStartNewThread()
  const button = (
    <button
      type="button"
      className={
        emailConnected ? "btn btn-primary" : "btn border border-neutral font-normal text-base-600 cursor-not-allowed"
      }
      data-test-id="compose-form"
      // Drop the hotkey when disabled so pressing "c" doesn't compose either.
      data-hotkey={emailConnected ? "c" : undefined}
      aria-disabled={!emailConnected}
      onClick={() => {
        // Compose creates an email thread; there's nothing to send from until email is
        // connected, so block the action and let the tooltip explain why.
        if (!emailConnected) return
        void startNewThread()
      }}
    >
      <span className="material-symbols-outlined text-base">edit</span>
      Compose
    </button>
  )

  if (emailConnected) return button
  return <Tooltip content="Connect email to compose">{button}</Tooltip>
}

export function Header({
  view,
  sort,
  allViews,
  hasGoalsForView,
  active,
  onboardingAvailable,
  emailConnected,
  createView,
  updateView,
  deleteView,
}: HeaderProps) {
  const isMobile = useIsMobile()
  return (
    <StickyHeader>
      <div className="flex items-center justify-between gap-2 p-2">
        <div className="flex min-w-0 items-center gap-2">
          <FilterDropdown view={view} />
          {/* Plain Newest/Oldest sort is desktop-only; on mobile the Focus menu is the
              inbox-ordering entry point (matches the PR #8095 mock). */}
          {view === "inbox" && !isMobile && <SortDropdown sort={sort} />}
          {/* TEMP: superuser guard disabled — `isSuperuser` should gate this. Restore before GA. */}
          {view === "inbox" && (
            <FocusDropdown
              allViews={allViews}
              active={active}
              hasGoalsForView={hasGoalsForView}
              onboardingAvailable={onboardingAvailable}
              createView={createView}
              updateView={updateView}
              deleteView={deleteView}
            />
          )}
        </div>
        <div className="flex items-center gap-2">
          <ComposeButton emailConnected={emailConnected} />
        </div>
      </div>
    </StickyHeader>
  )
}
