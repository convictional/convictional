import { Link } from "@tanstack/react-router"
import { type MouseEventHandler, type ReactNode, useState } from "react"

import { useIsMobile } from "~/react/shared/hooks/useIsMobile"

import { type EntryTarget, entryTargetWithReturnTo } from "../entryTarget"
import type { MailboxMutations } from "../hooks/useMailboxMutations"
import { useSwipeGesture } from "../hooks/useSwipeGesture"
import type { MailboxEntry } from "../types"
import { ChatEntryBody } from "./entryBodies/ChatEntryBody"
import { EmailThreadEntryBody } from "./entryBodies/EmailThreadEntryBody"
import { GoalEntryBody } from "./entryBodies/GoalEntryBody"
import { PostEntryBody } from "./entryBodies/PostEntryBody"
import { HoverActionBar } from "./HoverActionBar"

interface EntryRowProps {
  entry: MailboxEntry
  isSelected: boolean
  mutations: MailboxMutations
  onClick: () => void
  onArchive: () => void
  onSnooze: (snoozedUntil: string) => Promise<void>
  snoozeOpen: boolean
  onSnoozeOpenChange: (open: boolean) => void
  timezone: string | null
  // Set when this row slid under a stationary cursor after a list change, so the
  // browser won't re-fire :hover/mouseenter on its own. See useHoverRecovery (#8878).
  forceHover?: boolean
}

function desktopIndicator(entry: MailboxEntry, isSelected: boolean): ReactNode {
  if (isSelected) {
    return <div className="w-1.5 h-8 bg-primary rounded-full" />
  }
  if (entry.is_unread) {
    return <div className="w-1.5 h-1.5 bg-info-content rounded-full" />
  }
  return null
}

// The row's primary target. Entry hrefs are concrete paths (/chats/{id}), so this
// takes a runtime `to` rather than a typed route template — and can't use NavLink,
// whose routesByPath lookup only matches static paths. A target-less entry keeps
// rendering the dead anchor the API's "#" href produced.
function EntryLink({
  target,
  className,
  onClick,
  onClickCapture,
  children,
}: {
  target: EntryTarget | null
  className: string
  onClick: MouseEventHandler<HTMLAnchorElement>
  onClickCapture?: MouseEventHandler<HTMLAnchorElement>
  children: ReactNode
}) {
  if (!target) {
    return (
      <a href="#" className={className} onClick={onClick} onClickCapture={onClickCapture}>
        {children}
      </a>
    )
  }
  return (
    <Link
      to={target.to}
      search={target.search}
      className={className}
      onClick={onClick}
      onClickCapture={onClickCapture}
    >
      {children}
    </Link>
  )
}

function renderBody(entry: MailboxEntry): ReactNode {
  switch (entry.resource_type) {
    case "Chat":
      return <ChatEntryBody entry={entry} />
    case "EmailThread":
      return <EmailThreadEntryBody entry={entry} />
    case "Post":
      return <PostEntryBody entry={entry} />
    case "Goal":
      return <GoalEntryBody entry={entry} />
    default:
      return null
  }
}

export function EntryRow({
  entry,
  isSelected,
  mutations,
  onClick,
  onArchive,
  onSnooze,
  snoozeOpen,
  onSnoozeOpenChange,
  timezone,
  forceHover = false,
}: EntryRowProps) {
  const isMobile = useIsMobile()
  const [isHovered, setIsHovered] = useState(false)
  const target = entryTargetWithReturnTo(entry.href)
  const swipe = useSwipeGesture({
    enabled: isMobile,
    onCommit: onArchive,
  })

  const dataAttrs = {
    "data-test-id": `mailbox-entry-${entry.id}`,
    "data-thread-id": entry.id,
    "data-is-unread": entry.is_unread ? "true" : "false",
    "data-is-archived": entry.is_archived ? "true" : "false",
  }

  if (isMobile) {
    return (
      <li id={`mailbox-entry-${entry.id}`} className="thread-item">
        <div
          {...dataAttrs}
          className="relative overflow-hidden rounded-lg touch-pan-y"
          onTouchStart={swipe.handlers.onTouchStart}
          onTouchMove={swipe.handlers.onTouchMove}
          onTouchEnd={swipe.handlers.onTouchEnd}
          onTouchCancel={swipe.handlers.onTouchCancel}
        >
          {swipe.swipeDistance > 0 && (
            <div
              className={`absolute inset-0 flex items-center pr-6 pl-6 transition-colors duration-150 ease-out ${
                swipe.swipeProgress >= 1 ? "bg-info" : "bg-base-300"
              } ${swipe.swipeDirection === "left" ? "justify-end" : "justify-start"}`}
              style={{ opacity: swipe.swipeProgress }}
            >
              <div
                className="flex items-center gap-2"
                style={{ transform: `scale(${0.6 + swipe.swipeProgress * 0.4})` }}
              >
                <span className="material-symbols-outlined text-3xl text-primary-content">
                  {entry.is_archived ? "unarchive" : "archive"}
                </span>
              </div>
            </div>
          )}
          <div
            className={`relative will-change-transform ${
              swipe.isSwiping
                ? "transition-none"
                : "transition-transform duration-[220ms] ease-[cubic-bezier(0.32,0.72,0,1)]"
            }`}
            style={{ transform: `translate3d(${swipe.swipeX}px, 0, 0)` }}
          >
            <EntryLink
              target={target}
              className="grid grid-cols-[auto_1fr] gap-2 items-center p-3 bg-base-100"
              onClick={e => {
                if (swipe.isSwiping || swipe.swipeDistance > 0) {
                  e.preventDefault()
                  return
                }
                onClick()
              }}
              onClickCapture={swipe.handlers.onClickCapture}
            >
              <div className="w-3 flex items-center justify-center">
                {entry.is_unread && <div className="w-2 h-2 rounded-full bg-info-content" />}
              </div>
              <div className="min-w-0">
                <div className="min-w-0">{renderBody(entry)}</div>
              </div>
            </EntryLink>
          </div>
        </div>
      </li>
    )
  }

  return (
    <li id={`mailbox-entry-${entry.id}`} className="thread-item">
      <div
        {...dataAttrs}
        className={`group cursor-pointer transition-all grid grid-cols-[1fr_auto] hover:bg-base-300 rounded-lg relative overflow-hidden ${
          forceHover ? "bg-base-300" : ""
        }`}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <EntryLink
          target={target}
          className="grid grid-cols-[auto_1fr] gap-2 items-center p-2 min-w-0"
          onClick={onClick}
        >
          <div className="w-3 flex items-center justify-center">{desktopIndicator(entry, isSelected)}</div>
          <div className="min-w-0">
            <div className="min-w-0">{renderBody(entry)}</div>
          </div>
        </EntryLink>
        <div
          data-hover-actions
          className={`items-center gap-4 p-2 group-hover:flex ${snoozeOpen || forceHover ? "flex" : "hidden"}`}
          onClick={e => e.stopPropagation()}
        >
          {/* Mount the action bar (and its floating-ui tooltips) only while the
              row is hovered or its snooze dropdown is open. The bar is
              display:none otherwise, so rendering it for every row would build
              three to four floating-ui instances per row that no one can see. */}
          {(isHovered || snoozeOpen || forceHover) && (
            <HoverActionBar
              entry={entry}
              mutations={mutations}
              onArchive={onArchive}
              onSnooze={onSnooze}
              snoozeOpen={snoozeOpen}
              onSnoozeOpenChange={onSnoozeOpenChange}
              timezone={timezone}
            />
          )}
        </div>
      </div>
    </li>
  )
}
