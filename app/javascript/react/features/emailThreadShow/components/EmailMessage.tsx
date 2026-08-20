import { useQuery, useQueryClient } from "@tanstack/react-query"
import { memo, useCallback, useMemo, useState } from "react"
import type { Ref } from "react"

import { EmailMessageBody } from "~/react/composites/EmailMessageBody"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import type { EmailMessageSummary } from "~/react/shared/types"
import { DateTime } from "~/react/ui/DateTime"
import { LinkifiedText } from "~/react/ui/LinkifiedText"

import { emailMessageContentQueryOptions } from "../queries"
import { EmailMessageActions } from "./EmailMessageActions"
import { EmailMessageMenu } from "./EmailMessageMenu"
import { RecipientLine } from "./RecipientLine"

interface EmailMessageProps {
  message: EmailMessageSummary
  // Whether this is the last (most recent) message in the timeline. Drives
  // showing the primary action row at the bottom and which dropdown items
  // appear (the dropdown is suppressed for the last message because it has
  // its own action row).
  isLastMessage: boolean
  // Whether the current user can reply to this thread. Derived from
  // thread.can_reply on the parent.
  canReply: boolean
  // Whether to show "View Original" in the overflow menu (superuser-only).
  isSuperuser: boolean
  // Whether to render in the collapsed state on mount. Older messages start
  // collapsed; the most recent ones expand by default. Lazy-loaded content
  // is fetched on first expand for collapsed messages.
  startCollapsed: boolean
  // When true, this message is a row inside the collapsed group's single bordered
  // container, so it drops its own border/rounding/shadow to sit level with the
  // other rows (the container draws the frame and the row separators). See Timeline.
  inGroup?: boolean
  currentUserEmail: string | null
  // Handlers take the message id so Timeline can pass a single stable
  // reference per handler instead of allocating per-message arrow closures
  // on every render (which would defeat React.memo on this component).
  onReply: (messageId: string) => void
  onReplyAll: (messageId: string) => void
  onForward: (messageId: string) => void
  // Callback ref the parent sets only on the initial-scroll target. React 19 passes
  // ref as a plain prop — no forwardRef.
  ref?: Ref<HTMLDivElement>
}

const initialsFor = (name: string): string => {
  const stripped = name.replace(/[^a-zA-Z0-9]/g, "")
  return (stripped[0] ?? "").toUpperCase()
}

function EmailMessageImpl({
  message,
  isLastMessage,
  canReply,
  isSuperuser,
  startCollapsed,
  inGroup,
  currentUserEmail,
  onReply,
  onReplyAll,
  onForward,
  ref,
}: EmailMessageProps) {
  const [collapsed, setCollapsed] = useState(startCollapsed)
  const queryClient = useQueryClient()
  // The timeline (and the new-message broadcast) carry no body — it's an immutable
  // sub-resource fetched on demand from content_url, cached per message id. The
  // thread's load-time batch seeds this key so the initial expanded set is a cache
  // hit (no per-message fetch); a message expanded later, hover-prefetched, or
  // realtime-added is a cache miss that fetches here. Disabled while collapsed so a
  // collapsed message never fetches until first expand.
  const contentQuery = useQuery({
    ...emailMessageContentQueryOptions(message.id, message.content_url),
    enabled: !collapsed,
  })
  const content = contentQuery.data ?? null
  const error = contentQuery.isError

  const toggle = useCallback(() => {
    // Re-expanding after a failed load retries the fetch (staleTime: Infinity leaves
    // the errored, data-less query untouched otherwise).
    if (collapsed && contentQuery.isError) void contentQuery.refetch()
    setCollapsed(prev => !prev)
  }, [collapsed, contentQuery])

  // Hover-prefetch for collapsed messages: warming the content cache before the click
  // lands makes the expand feel instant. prefetchQuery is a no-op once the body is
  // cached (staleTime: Infinity) or a fetch is already in flight.
  const prefetch = useCallback(() => {
    if (!collapsed) return
    void queryClient.prefetchQuery(emailMessageContentQueryOptions(message.id, message.content_url))
  }, [collapsed, queryClient, message.id, message.content_url])

  const messageId = message.id
  const handleReply = useCallback(() => onReply(messageId), [onReply, messageId])
  const handleReplyAll = useCallback(() => onReplyAll(messageId), [onReplyAll, messageId])
  const handleForward = useCallback(() => onForward(messageId), [onForward, messageId])
  const handleMenuReply = useCallback(
    (replyType: "reply" | "reply_all") => (replyType === "reply" ? handleReply() : handleReplyAll()),
    [handleReply, handleReplyAll]
  )

  const datetime = message.received_at ?? message.sent_at ?? message.created_at
  const isMobile = useIsMobile()
  const showMenu = canReply || isSuperuser
  // The dropdown is hidden on the last message because the primary action
  // row below covers Reply / Reply All / Forward. Superuser-only "View
  // Original" remains accessible from earlier messages.
  const showDropdownReplyItems = canReply && !isLastMessage
  const visibleAttachments = useMemo(() => (content?.attachments ?? []).filter(a => a.show_in_list), [content])

  return (
    <div
      ref={ref}
      className={
        inGroup
          ? "email-message scroll-mt-[150px] bg-base-50 overflow-hidden"
          : "email-message scroll-mt-[150px] bg-base-50 border rounded-xl overflow-hidden border-base-300 shadow-xs"
      }
      data-message-id={message.id}
      onMouseEnter={prefetch}
      onFocus={prefetch}
    >
      <div
        onClick={toggle}
        className={`grid grid-cols-[1fr_auto] items-center gap-2 p-3 sm:p-2 cursor-pointer ${
          collapsed ? "rounded-xl" : "rounded-t-xl border-b border-base-300"
        }`}
        aria-expanded={!collapsed}
      >
        <div className="flex items-center gap-2 min-w-0">
          <div className="avatar avatar-placeholder static border-4 border-base-200 rounded-full">
            <div className="w-6 h-6 text-sm rounded-full bg-neutral-300 text-neutral-600">
              <span className="uppercase">{initialsFor(message.sender_name)}</span>
            </div>
          </div>
          <div className="min-w-0">
            <div className="inline-flex gap-1 items-center">
              <span className="text-sm font-semibold">{message.sender_name}</span>
              <span className="text-xs text-base-500 hidden sm:inline">&lt;{message.sender_email}&gt;</span>
              <span className="text-xs text-base-500 inline sm:hidden">
                <DateTime datetime={datetime} />
              </span>
            </div>
            {/* Collapsed rows stay sparse (see sketch): the preview text takes the
                recipients' place rather than adding a third row below the header. */}
            {collapsed ? (
              <div className="text-xs text-base-600/70 truncate">{message.preview}</div>
            ) : (
              <RecipientLine to={message.to} cc={message.cc} currentUserEmail={currentUserEmail} />
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="text-xs hidden sm:block">
            <DateTime datetime={datetime} />
          </div>
          {showMenu && !collapsed && (
            <div onClick={e => e.stopPropagation()}>
              <EmailMessageMenu
                viewOriginalUrl={message.view_original_url}
                showReply={showDropdownReplyItems}
                showViewOriginal={isSuperuser}
                onReply={handleMenuReply}
                onForward={handleForward}
              />
            </div>
          )}
          <div className="ml-2 hidden sm:block">
            <span className="material-symbols-outlined text-base transition-transform duration-200">
              {collapsed ? "expand_all" : "collapse_all"}
            </span>
          </div>
        </div>
      </div>
      {!collapsed && (
        <div className="text-xs overflow-hidden">
          {!content && !error && (
            // Awaiting the body — the per-message content query is fetching it.
            <div className="p-4">
              <span className="loading loading-spinner loading-xs" />
            </div>
          )}
          {error && <div className="p-4 text-error">Failed to load message content</div>}
          {content && !error && (
            <>
              {content.content_html ? (
                <EmailMessageBody
                  contentHtml={content.content_html}
                  isMobile={isMobile}
                  isAuthored={message.message_type !== "received"}
                />
              ) : content.body_plain ? (
                <div className="whitespace-pre-wrap p-4">
                  <LinkifiedText text={content.body_plain} />
                </div>
              ) : (
                <div className="text-base-400 italic p-4">No content</div>
              )}
              {visibleAttachments.length > 0 && (
                <ul className="text-sm">
                  {visibleAttachments.map(a => (
                    <li
                      key={a.id}
                      data-testid="email-attachment"
                      className="px-4 py-2 border-t border-base-300 flex items-center gap-2"
                    >
                      {/* Same-origin file download: opt out of HTMX boost so the
                          browser downloads it instead of AJAX-swapping the bytes. */}
                      <a href={a.download_url} className="flex items-center gap-2 min-w-0" data-hx-boost="false">
                        <span className="material-symbols-outlined text-sm flex-shrink-0">attach_file</span>
                        <span className="underline truncate min-w-0">{a.filename}</span>
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
      {isLastMessage && canReply && !collapsed && (
        <EmailMessageActions onReply={handleReply} onReplyAll={handleReplyAll} onForward={handleForward} />
      )}
    </div>
  )
}

export const EmailMessage = memo(EmailMessageImpl)
