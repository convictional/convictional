import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"

import { InteractiveMessageBubble } from "~/react/composites/chat/InteractiveMessageBubble"
import { JumpToLatestPill } from "~/react/composites/chat/JumpToLatestPill"
import { UnreadDivider } from "~/react/composites/UnreadDivider"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import { isContinuation } from "~/react/shared/messageGrouping"
import type { ChatCollaborator, ChatMessage, ChatType, Decision, ReplyPreview } from "~/react/shared/types"
import { pluralize } from "~/shared/strings"

import { GroupChatEmptyState } from "./GroupChatEmptyState"

// Dispatched before any programmatic window scroll from an island. The
// reveal-on-scroll nav controller (useRevealNavOnScroll) listens and suppresses
// its own animation for a short window so its sticky-`top` transitions don't
// fire mid-pin (the WebKit scroll-anchor algorithm reacts to those layout
// shifts and drags scrollY backwards). Page-neutral name since the listener
// lives in react/shared/.
const PROGRAMMATIC_SCROLL_EVENT = "island:programmatic-scroll"
function notifyProgrammaticScroll() {
  window.dispatchEvent(new CustomEvent(PROGRAMMATIC_SCROLL_EVENT))
}

const LOAD_MORE_LOOKAHEAD_PX = 1000

// Pin to the normal scroll maximum, not scrollHeight: with the iOS keyboard
// open, Safari extends the scrollable range by roughly the keyboard height so
// content behind the keyboard can be reached. scrollTo(scrollHeight) lands in
// that extension, dragging the document end — and the in-flow compose bar —
// up past the keyboard. Sticky never pushes an element below its flow
// position, so the bar beaches there with dead space under it. Outside the
// extension the two targets clamp to the same place.
function scrollToBottomEdge(behavior: ScrollBehavior) {
  window.scrollTo({ top: document.documentElement.scrollHeight - window.innerHeight, behavior })
}

interface MessageListProps {
  messages: ChatMessage[]
  loadingMore: boolean
  hasMore: boolean
  currentUserId: string
  chatTitle: string
  chatType: ChatType
  isGroupChat: boolean
  // Group-chat empty state: members drive solo-vs-populated and the presence line.
  collaborators: ChatCollaborator[]
  memberCount: number
  onAddPeople: () => void
  onStartMessage: () => void
  editingMessageId: string | null
  lastReadAt: string | null
  unreadMessageCount: number
  uploadUrl: string | null
  mentionableUsers: MentionUser[]
  mentionsEnabled?: boolean
  klipyApiKey: string | null
  onLoadMore: () => Promise<void>
  // Forward pagination, fired when scrolled near the bottom while not at the
  // tail (the mirror of onLoadMore near the top); closes the gap to the live
  // tail page by page.
  onLoadNewer: () => Promise<void>
  loadingNewer: boolean
  hasNewer: boolean
  onScrollTo: (id: string) => void
  scrollingToReplyRef: React.RefObject<boolean>
  scrollingToId: string | null
  // Loaded bottom is the live tail. When false the list is a not-caught-up
  // historical window (quote-reply jump): sticky-bottom is gated off and the
  // pill offers a fast-skip back to the tail.
  atTail: boolean
  onJumpToLatest: () => void
  onEdit: (messageId: string) => void
  onCancelEdit: () => void
  onSaveEdit: (
    messageId: string,
    content: string,
    attachmentClaimId: string | null,
    retainedAttachmentIds: string[]
  ) => Promise<void>
  onDelete: (messageId: string) => void
  onReact: (messageId: string, reactionType: string) => void
  onReply: (reply: ReplyPreview) => void
  // Decisions keyed by comment_gid; drives the inline DecisionMarker per message.
  decisionsByGid: Map<string, Decision>
  onToggleDecision: (commentGid: string) => void
}

export function MessageList({
  messages,
  loadingMore,
  hasMore,
  currentUserId,
  chatTitle,
  chatType,
  isGroupChat,
  collaborators,
  memberCount,
  onAddPeople,
  onStartMessage,
  editingMessageId,
  lastReadAt,
  unreadMessageCount,
  uploadUrl,
  mentionableUsers,
  mentionsEnabled,
  klipyApiKey,
  onLoadMore,
  onLoadNewer,
  loadingNewer,
  hasNewer,
  onScrollTo,
  scrollingToReplyRef,
  scrollingToId,
  atTail,
  onJumpToLatest,
  onEdit,
  onCancelEdit,
  onSaveEdit,
  onDelete,
  onReact,
  onReply,
  decisionsByGid,
  onToggleDecision,
}: MessageListProps) {
  const sentinelRef = useRef<HTMLDivElement>(null)
  const bottomSentinelRef = useRef<HTMLDivElement>(null)
  const dividerRef = useRef<HTMLDivElement>(null)
  const messagesWrapperRef = useRef<HTMLDivElement>(null)
  // Manual prepend compensation (see the load-more layout effect): document
  // scroll anchoring is disabled (useDisableDocumentScrollAnchor), so growing
  // the document above the viewport would otherwise leave scrollY fixed and
  // jump the user up by a page. Holds the first message id captured when an
  // organic scroll-up load-more fires; compensation runs only once that id
  // actually changes, i.e. a page was really prepended. Anchoring on the id
  // (rather than a boolean flag) means a failed load — which never changes
  // `messages` — can't leave a stale flag that misfires on the next incoming
  // message, and a message appended mid-fetch isn't mistaken for a prepend.
  const prependAnchorRef = useRef<string | null>(null)
  const prevScrollHeightRef = useRef(0)
  const lastMessageId = messages[messages.length - 1]?.id
  // Latest first message id, read by the load-more observer callback (whose
  // closure over `messages` would otherwise go stale after a prepend, since
  // `messages` isn't in its dependency array).
  const firstMessageIdRef = useRef(messages[0]?.id)
  firstMessageIdRef.current = messages[0]?.id
  const [autoScroll, setAutoScroll] = useState(true)
  const [hasNewMessages, setHasNewMessages] = useState(false)
  const [scrollingToUnread, setScrollingToUnread] = useState(false)
  const prevLastMessageIdRef = useRef(lastMessageId)
  const autoScrollRef = useRef(autoScroll)
  useEffect(() => {
    autoScrollRef.current = autoScroll
  }, [autoScroll])
  // Mirror atTail into a ref so the sticky-bottom effects (which run off
  // ResizeObserver/rAF callbacks created once) read the current value rather
  // than the one captured at effect setup.
  const atTailRef = useRef(atTail)
  atTailRef.current = atTail

  // Disable browser scroll restoration so a back-nav doesn't fight our pin.
  useEffect(() => {
    const prev = history.scrollRestoration
    history.scrollRestoration = "manual"
    return () => {
      history.scrollRestoration = prev
    }
  }, [])

  // Sticky-bottom: while autoScroll is true, re-pin to the bottom whenever the
  // messages wrapper changes height. This handles the cold-cache case where
  // images inside <Markdown> (rendered from message.content) settle after
  // first paint, as well as any other late layout changes from new messages or
  // DOM mutations. Prepend pagination is held in place by the manual
  // compensation in the load-more layout effect below (document scroll
  // anchoring is disabled); this hook handles bottom-pinning.
  useEffect(() => {
    const el = messagesWrapperRef.current
    if (!el) return
    const pinIfBottom = () => {
      // Don't pin to a not-caught-up window's bottom — that bottom is not the
      // live tail, so auto-scrolling there would defeat the jump.
      if (!atTailRef.current) return
      if (!autoScrollRef.current) return
      notifyProgrammaticScroll()
      scrollToBottomEdge("instant")
    }
    pinIfBottom()
    const ro = new ResizeObserver(pinIfBottom)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // For a brand-new last message, decide between auto-scroll and the
  // "new messages" indicator. When autoScroll is true the ResizeObserver will
  // pin us; when it's false (user scrolled up) we surface the indicator.
  useEffect(() => {
    const prevLastId = prevLastMessageIdRef.current
    prevLastMessageIdRef.current = lastMessageId
    if (!lastMessageId || lastMessageId === prevLastId) return
    // While not at the tail, a changing last id is a window swap or a forward
    // page (jump / load-newer), not a live append, so it must not pin.
    if (!atTailRef.current) return

    const lastMessage = messages[messages.length - 1]
    const isOwnMessage = lastMessage?.user.id === currentUserId

    if (isOwnMessage) {
      // Sending pulls the user back to the bottom even if they had scrolled up.
      requestAnimationFrame(() => {
        notifyProgrammaticScroll()
        scrollToBottomEdge("instant")
      })
      return
    }
    if (!autoScrollRef.current) {
      setHasNewMessages(true)
    }
  }, [lastMessageId, messages, currentUserId])

  // "Jump to latest" reloads the live tail while the user is scrolled up
  // (autoScroll false), so the autoScroll-gated pins above never fire. Snap to
  // the bottom explicitly on the atTail false->true edge; re-arming autoScroll
  // also disarms the load-older observer so no older page prepends.
  //
  // Forward pagination (loadNewer) also flips atTail false->true on reaching the
  // tail, but it keeps the user where they are mid-thread — snapping there would
  // be jarring. So this only fires when the list shrank to a fresh page (the
  // jumpToLatest reload replaces the window), not when it grew via loadNewer.
  const prevAtTailRef = useRef(atTail)
  const prevMessageCountRef = useRef(messages.length)
  useEffect(() => {
    const wasAtTail = prevAtTailRef.current
    const prevCount = prevMessageCountRef.current
    prevAtTailRef.current = atTail
    prevMessageCountRef.current = messages.length
    if (wasAtTail || !atTail) return
    // loadNewer only appends, so the count grows; a jumpToLatest reload replaces
    // the window with the newest page (count does not grow from the window).
    if (messages.length > prevCount) return
    setHasNewMessages(false)
    setAutoScroll(true)
    notifyProgrammaticScroll()
    scrollToBottomEdge("instant")
  }, [atTail, messages.length])

  // Track scroll position for auto-scroll detection.
  useEffect(() => {
    function handleScroll() {
      const nearBottom = Math.abs(document.documentElement.scrollHeight - window.scrollY - window.innerHeight) < 50
      setAutoScroll(prev => (prev === nearBottom ? prev : nearBottom))
      if (nearBottom) setHasNewMessages(false)
    }
    window.addEventListener("scroll", handleScroll, { passive: true })
    return () => window.removeEventListener("scroll", handleScroll)
  }, [])

  // Hold the viewport in place when load-more prepends older messages. Runs
  // before paint: measure how much the document grew since the last commit and
  // shift scrollY by that delta so the previously-visible content stays put.
  // The delta cancels the transient load-more spinner (it toggles `loadingMore`
  // without changing `messages`, so it never updates the height ref) and
  // respects any scrolling the user did during the fetch (reads live scrollY).
  // Only the organic scroll-up path sets the flag; scrollToUnread and
  // scrollToReply end with their own scrollIntoView, so they must not be offset.
  useLayoutEffect(() => {
    const newHeight = document.documentElement.scrollHeight
    const anchor = prependAnchorRef.current
    if (anchor !== null && messages[0]?.id !== anchor) {
      prependAnchorRef.current = null
      const delta = newHeight - prevScrollHeightRef.current
      if (delta > 0) {
        notifyProgrammaticScroll()
        window.scrollTo({ top: window.scrollY + delta, behavior: "instant" })
      }
    }
    prevScrollHeightRef.current = newHeight
  }, [messages])

  // Intersection observer for load-more sentinel. The re-entrancy gate is owned
  // here (not derived from the `loadingMore` prop) because the parent flips that
  // flag asynchronously inside `onLoadMore`. Claiming the ref synchronously
  // closes the window where two callbacks both see `loadingMore === false` — a
  // window that widens with the 1000px rootMargin and with `scrollToUnread`'s
  // own loop calling `onLoadMore` in parallel. The cleanup also resets the gate
  // so a new observer created after the user returns to the bottom and scrolls
  // back up is not blocked by a still-pending promise from the prior observer.
  const paginatingRef = useRef(false)
  useEffect(() => {
    const el = sentinelRef.current
    if (!el || !hasMore || autoScroll) return // only observe when user has scrolled away from the bottom

    const observer = new IntersectionObserver(
      entries => {
        if (!entries[0].isIntersecting) return
        if (scrollingToReplyRef.current) return
        if (paginatingRef.current) return
        paginatingRef.current = true
        prependAnchorRef.current = firstMessageIdRef.current ?? null
        onLoadMore().finally(() => {
          paginatingRef.current = false
        })
      },
      { threshold: 0, rootMargin: `${LOAD_MORE_LOOKAHEAD_PX}px 0px 0px 0px` }
    )
    observer.observe(el)
    return () => {
      paginatingRef.current = false
      observer.disconnect()
    }
  }, [autoScroll, hasMore, onLoadMore, scrollingToReplyRef])

  // Forward-pagination observer, the mirror of the load-more one above: while
  // not at the tail, intersecting the bottom sentinel pulls the next NEWER page
  // to close the gap to the live tail. Same self-owned re-entrancy gate, since
  // the parent flips `loadingNewer` asynchronously. When loadNewer reaches the
  // tail it flips atTail true, this effect tears down, and live append resumes.
  const paginatingNewerRef = useRef(false)
  useEffect(() => {
    const el = bottomSentinelRef.current
    if (!el || atTail) return

    const observer = new IntersectionObserver(
      entries => {
        if (!entries[0].isIntersecting) return
        if (scrollingToReplyRef.current) return
        if (paginatingNewerRef.current) return
        paginatingNewerRef.current = true
        onLoadNewer().finally(() => {
          paginatingNewerRef.current = false
        })
      },
      { threshold: 0, rootMargin: `0px 0px ${LOAD_MORE_LOOKAHEAD_PX}px 0px` }
    )
    observer.observe(el)
    return () => {
      paginatingNewerRef.current = false
      observer.disconnect()
    }
  }, [atTail, onLoadNewer, scrollingToReplyRef])

  const scrollToBottom = useCallback(() => {
    setHasNewMessages(false)
    setAutoScroll(true)
    notifyProgrammaticScroll()
    scrollToBottomEdge("smooth")
  }, [])

  // Index of the first unread message. The divider renders before this message.
  // Skip if lastReadAt is null (never read) or no unread messages.
  const newMessagesDividerIndex = useMemo(() => {
    if (!lastReadAt || unreadMessageCount === 0) return -1
    const idx = messages.findIndex(m => m.created_at > lastReadAt)
    // Don't show divider at position 0 — it would be above all loaded messages
    // and provides no useful separation
    return idx > 0 ? idx : -1
  }, [messages, lastReadAt, unreadMessageCount])

  // Show the "unread messages" button when every loaded message is unread and
  // older pages still exist — the divider can't render yet because it would be
  // at position 0, so loading older pages will eventually reveal it.
  const hasHiddenUnread =
    lastReadAt !== null &&
    unreadMessageCount > 0 &&
    newMessagesDividerIndex === -1 &&
    messages.length > 0 &&
    messages[0].created_at > lastReadAt &&
    hasMore

  // Keep a ref to hasMore so the async scrollToUnread loop reads the latest
  // value instead of the one captured when the callback was created.
  const hasMoreRef = useRef(hasMore)
  hasMoreRef.current = hasMore

  const scrollToUnread = useCallback(async () => {
    if (scrollingToUnread) return
    setScrollingToUnread(true)
    // Hold the pagination gate so the IntersectionObserver doesn't fire its own
    // `onLoadMore` while this loop is mid-await — that would issue overlapping
    // page requests against the same cursor.
    paginatingRef.current = true
    try {
      let attempts = 0
      while (!dividerRef.current && hasMoreRef.current && attempts < 50) {
        await onLoadMore()
        // Two rAFs to let React commit the prepended messages (and the divider,
        // once it's in range) before the next loop iteration checks the ref.
        await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
        attempts++
      }
      if (dividerRef.current) {
        notifyProgrammaticScroll()
        dividerRef.current.scrollIntoView({ behavior: "smooth", block: "center" })
      }
    } finally {
      paginatingRef.current = false
      setScrollingToUnread(false)
    }
  }, [scrollingToUnread, onLoadMore])

  return (
    <>
      <div ref={messagesWrapperRef} className="grid pl-3 pr-2 pb-4">
        {hasMore && (
          <div ref={sentinelRef} className="flex justify-center py-4">
            {loadingMore && <span className="loading loading-spinner loading-sm" />}
          </div>
        )}
        {!hasMore && messages.length > 0 && (
          <div className="text-center text-base-content/40 text-xs py-6">
            {chatType === "self"
              ? `Beginning of ${chatTitle}`
              : isGroupChat
                ? `Beginning of chat in ${chatTitle}`
                : `Beginning of chat with ${chatTitle}`}
          </div>
        )}
        {messages.length === 0 &&
          (isGroupChat ? (
            <GroupChatEmptyState
              chatTitle={chatTitle}
              isSolo={memberCount <= 1}
              collaborators={collaborators}
              currentUserId={currentUserId}
              onAddPeople={onAddPeople}
              onStartMessage={onStartMessage}
            />
          ) : (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <p className="text-base-500 text-sm">
                {chatType === "self"
                  ? "Jot down notes, park links, or draft messages"
                  : `Start a conversation with ${chatTitle}`}
              </p>
            </div>
          ))}
        {messages.map((msg, i) => {
          const grouped = i === newMessagesDividerIndex ? false : isContinuation(messages[i - 1], msg)
          return (
            <React.Fragment key={msg.id}>
              {i === newMessagesDividerIndex && (
                <UnreadDivider ref={dividerRef} count={unreadMessageCount} noun="message" />
              )}
              <InteractiveMessageBubble
                className={i === 0 ? "" : grouped ? "mt-0.5" : "mt-2"}
                message={msg}
                currentUserId={currentUserId}
                isGrouped={grouped}
                isEditing={editingMessageId === msg.id}
                chatType={chatType}
                uploadUrl={uploadUrl}
                mentionableUsers={mentionableUsers}
                mentionsEnabled={mentionsEnabled}
                klipyApiKey={klipyApiKey}
                onScrollTo={onScrollTo}
                scrollingToId={scrollingToId}
                onEdit={onEdit}
                onCancelEdit={onCancelEdit}
                onSaveEdit={onSaveEdit}
                onDelete={onDelete}
                onReact={onReact}
                onReply={onReply}
                decision={decisionsByGid.get(msg.global_id)}
                onToggleDecision={onToggleDecision}
              />
            </React.Fragment>
          )
        })}
        {/* Forward-pagination sentinel: only present (and observed) while not at
            the tail, where intersecting it loads the next newer page. */}
        {!atTail && hasNewer && (
          <div ref={bottomSentinelRef} className="flex justify-center py-4">
            {loadingNewer && <span className="loading loading-spinner loading-sm" />}
          </div>
        )}
      </div>

      {/* One pill, two states. Not at the tail (a historical-window jump): a
          fast-skip back to the live tail, since scrolling forward could be many
          pages. At the tail but scrolled up with a new message below the fold:
          scroll down to it. */}
      {(!atTail || (hasNewMessages && !autoScroll)) && (
        <div className="fixed bottom-[calc(5rem+var(--safe-area-inset-bottom))] left-1/2 transform -translate-x-1/2 z-20">
          {!atTail ? (
            <JumpToLatestPill onClick={onJumpToLatest} label="Jump to latest" variant="latest" />
          ) : (
            <JumpToLatestPill onClick={scrollToBottom} label="New messages" />
          )}
        </div>
      )}

      {hasHiddenUnread && (
        <div className="fixed bottom-[calc(5rem+var(--safe-area-inset-bottom))] left-1/2 transform -translate-x-1/2 z-20">
          <button
            onClick={scrollToUnread}
            disabled={scrollingToUnread}
            className="btn btn-primary btn-sm rounded-full shadow-lg flex items-center gap-2"
          >
            {scrollingToUnread ? (
              <span className="loading loading-spinner loading-xs" />
            ) : (
              <span className="material-symbols-outlined text-sm">keyboard_arrow_up</span>
            )}
            <span>
              {unreadMessageCount > 99 ? "99+" : unreadMessageCount} unread {pluralize(unreadMessageCount, "message")}
            </span>
          </button>
        </div>
      )}
    </>
  )
}
