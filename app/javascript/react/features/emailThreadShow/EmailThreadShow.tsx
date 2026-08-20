import { useQuery, useQueryClient } from "@tanstack/react-query"
import { getRouteApi } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { TypingIndicator } from "~/react/composites/chat/TypingIndicator"
import type { CommentComposerFocusHandle } from "~/react/composites/comment/CommentComposer"
import { EmailComposer } from "~/react/composites/emailComposer/EmailComposer"
import type { SendOptions } from "~/react/composites/emailComposer/types"
import { MAILBOX_ACTION_SEGMENT_CLASS, MailboxActionBar, mailboxActionUrls } from "~/react/composites/MailboxActionBar"
import type { MailboxState } from "~/react/composites/MailboxActionBar"
import { useMailboxEntryNavigation } from "~/react/composites/MailboxActionBar/useMailboxEntryNavigation"
import { RequestDocumentAccess } from "~/react/composites/RequestDocumentAccess"
import { WorkspaceAssignment } from "~/react/composites/WorkspaceAssignment"
import { WorkspaceCollaborators } from "~/react/composites/workspaceCollaborators/WorkspaceCollaborators"
import { accessDeniedUrl, ApiError, apiFetch } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDecisions } from "~/react/shared/hooks/useDecisions"
import { useDisableDocumentScrollAnchor } from "~/react/shared/hooks/useDisableDocumentScrollAnchor"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useReactionToggle } from "~/react/shared/hooks/useReactionToggle"
import { useReconnectCatchUp } from "~/react/shared/hooks/useReconnectCatchUp"
import { useRefocusOnEditClose } from "~/react/shared/hooks/useRefocusOnEditClose"
import { useScrollToHashComment } from "~/react/shared/hooks/useScrollToHashComment"
import { useViewportFillHeight } from "~/react/shared/hooks/useViewportFillHeight"
import { useWorkspaceVisitRecording } from "~/react/shared/hooks/useVisitRecording"
import { lastOwnItemId } from "~/react/shared/lastOwnItem"
import type {
  EmailMessageSummary,
  EmailThreadMailboxEntry,
  EmailThreadShowResponse,
  ReactionUser,
  ReplyPreview,
  TimelineItem,
  EmailThreadComment,
} from "~/react/shared/types"
import { Tooltip } from "~/react/ui/Tooltip"
import { showFlash } from "~/shared/flash"

import { DraftConflictDialog } from "./components/DraftConflictDialog"
import { EmailThreadCommentForm } from "./components/EmailThreadCommentForm"
import { EmailThreadHeader } from "./components/EmailThreadHeader"
import { EmailThreadTitle } from "./components/EmailThreadTitle"
import { HelpDialog } from "./components/HelpDialog"
import { Timeline } from "./components/Timeline"
import { EmailThreadSkeleton } from "./EmailThreadSkeleton"
import { useDraftSubjectListener } from "./hooks/useDraftSubjectListener"
import { useEmailThreadChannel } from "./hooks/useEmailThreadChannel"
import { useEmailThreadCommentsChannel } from "./hooks/useEmailThreadCommentsChannel"
import { useEmailThreadHotkeys } from "./hooks/useEmailThreadHotkeys"
import { useInitialScrollTarget } from "./hooks/useInitialScrollTarget"
import { useInitialThreadScroll } from "./hooks/useInitialThreadScroll"
import { useNewMessagesIndicator } from "./hooks/useNewMessagesIndicator"
import { useReplyComposer } from "./hooks/useReplyComposer"
import { useScrollToDraft } from "./hooks/useScrollToDraft"
import { useScrollToUnreadComment } from "./hooks/useScrollToUnreadComment"
import {
  isOwnWorkspaceEvent,
  useWorkspaceEventsChannel,
  type WorkspaceEventBroadcast,
} from "./hooks/useWorkspaceEventsChannel"
import { emailThreadQueryKey, emailThreadQueryOptions } from "./queries"
import { collapsedMessageIdsFor, unreadComments } from "./readState"
import { emailThreadBackNavigation } from "./urls"

// The route id carries the pathless shell parent prefix (shellRoute has id
// "shell"), so the typed accessor is addressed as "/shell/email_threads/$emailThreadId".
const routeApi = getRouteApi("/shell/email_threads/$emailThreadId")

interface PendingReply {
  url: string
  replyType: "reply" | "reply_all" | "forward"
}

function buildMailboxState(entry: EmailThreadMailboxEntry): MailboxState {
  return {
    isUnread: entry.is_unread,
    isArchived: entry.is_archived,
    isSnoozed: entry.is_snoozed,
    snoozedUntil: entry.snoozed_until,
  }
}

// Stable empty references for the loading window (before the envelope resolves),
// so the derived timeline/comments below keep a constant identity and don't churn
// the memos/effects that depend on them.
const EMPTY_TIMELINE: TimelineItem[] = []
const EMPTY_COMMENTS: EmailThreadComment[] = []

export function EmailThreadShow() {
  const { emailThreadId: threadId } = routeApi.useParams()
  const { return_to: returnTo } = routeApi.useSearch()
  const queryClient = useQueryClient()

  // The whole show envelope is one channel-first Query entry. The former
  // useState slices (timeline/comments/mailbox entry) are reads off it, and the
  // channel handlers / mutations below patch it with setQueryData. Distinct
  // threadIds keep distinct cache entries, so a neighbor-thread nav can't surface
  // the prior thread (the route also remounts on threadId).
  const query = useQuery(emailThreadQueryOptions(queryClient, threadId))
  const data = query.data ?? null
  const timeline = data?.timeline ?? EMPTY_TIMELINE
  const comments = data?.comments ?? EMPTY_COMMENTS
  const mailboxEntry = data?.mailbox_entry ?? null

  const [pendingReply, setPendingReply] = useState<PendingReply | null>(null)

  // The comment currently open for inline editing, or null. Owned here rather
  // than per-item so the bottom composer's Up-arrow can select the user's last
  // comment for editing, mirroring chat.
  const [editingCommentId, setEditingCommentId] = useState<string | null>(null)

  // The comment being quote-replied to, or null. Owned here alongside the edit
  // selection so the bottom composer's banner and the sent reply_to_id stay in
  // sync with the per-item Reply affordance.
  const [replyingTo, setReplyingTo] = useState<ReplyPreview | null>(null)

  const { user: currentUser } = useCurrentUser()
  const isMobile = useIsMobile()
  const composerRef = useRef<HTMLDivElement | null>(null)
  const commentComposerRef = useRef<CommentComposerFocusHandle | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  // Records the visit once per mount. The view remounts per thread (route keys on
  // emailThreadId), so a neighbor-thread navigation gets a fresh ref and records
  // its own visit.
  const trackedVisitRef = useRef(false)

  // The workspace id isn't a route param — it arrives with the show envelope. The
  // channel/visit/decision hooks below all no-op on an empty id and re-arm once it
  // resolves, so deriving it from `data` (rather than a bootstrap prop) is safe.
  const workspaceId = data?.thread.workspace_id ?? ""

  useDocumentTitle(data?.thread.title || "No subject")

  useDisableDocumentScrollAnchor()
  // Fill the viewport so the sticky comment composer sits at its bottom even
  // when a short thread doesn't scroll (the root only mounts once loaded).
  useViewportFillHeight(rootRef, !!data && !!mailboxEntry)

  // Patch the show envelope in the cache. The channel handlers and the mutations
  // below all spell their update as a pure transform of the cached envelope, so
  // the realtime and local-action paths stay identical (the useCommentThreads
  // pattern). A no-op if the entry is gone (unmounted / evicted).
  const patchThread = useCallback(
    (fn: (data: EmailThreadShowResponse) => EmailThreadShowResponse) =>
      queryClient.setQueryData<EmailThreadShowResponse>(emailThreadQueryKey(threadId), old => (old ? fn(old) : old)),
    [queryClient, threadId]
  )
  const setComments = useCallback(
    (update: EmailThreadComment[] | ((prev: EmailThreadComment[]) => EmailThreadComment[])) =>
      patchThread(d => ({ ...d, comments: typeof update === "function" ? update(d.comments) : update })),
    [patchThread]
  )
  const setMailboxEntry = useCallback(
    (update: (prev: EmailThreadMailboxEntry) => EmailThreadMailboxEntry) =>
      patchThread(d => ({ ...d, mailbox_entry: update(d.mailbox_entry) })),
    [patchThread]
  )

  // Recover broadcasts missed while this view was unmounted and its subscription
  // unwired — on socket reconnect and on a warm remount (a thread switch remounts
  // the view while the QueryClient singleton and socket survive). See useReconnectCatchUp.
  useReconnectCatchUp(emailThreadQueryKey(threadId), "emailThreadShow")

  // Record the workspace visit once, when the timeline first loads.
  const recordVisit = useWorkspaceVisitRecording(workspaceId)
  useEffect(() => {
    if (!data || trackedVisitRef.current) return
    trackedVisitRef.current = true
    recordVisit(data.last_event_id)
  }, [data, recordVisit])

  const newMessages = useNewMessagesIndicator({ initiallyNearBottom: !data?.mailbox_entry.is_unread })

  const handleMessageAdded = useCallback(
    (message: EmailMessageSummary) => {
      patchThread(d => {
        if (d.timeline.some(i => i.type === "message" && i.message.id === message.id)) return d
        return {
          ...d,
          timeline: [
            ...d.timeline,
            {
              type: "message",
              item_id: message.id,
              created_at: message.received_at ?? message.sent_at ?? message.created_at,
              message,
              event: null,
            },
          ],
        }
      })
      newMessages.notifyNewItem()
    },
    [patchThread, newMessages]
  )
  const handleEventAdded = useCallback(
    (event: WorkspaceEventBroadcast) => {
      // Comments now arrive natively on the email_thread_comments channel as
      // CREATED; skip the duplicate "commented" activity event here.
      if (event.eventAction === "commented") return
      // Other workspace_events broadcasts only carry ids; invalidate to pull in the
      // new activity event (a coarse event carries no row to patch).
      void queryClient.invalidateQueries({ queryKey: emailThreadQueryKey(threadId) })
      if (!isOwnWorkspaceEvent(event, currentUser?.id ?? null)) newMessages.notifyNewItem()
    },
    [queryClient, threadId, newMessages, currentUser?.id]
  )

  const appendComment = useCallback(
    (comment: EmailThreadComment) => {
      setComments(prev => (prev.some(c => c.id === comment.id) ? prev : [...prev, comment]))
    },
    [setComments]
  )
  const replaceComment = useCallback(
    (comment: EmailThreadComment) => {
      setComments(prev => prev.map(c => (c.id === comment.id ? comment : c)))
    },
    [setComments]
  )
  const removeComment = useCallback(
    (commentId: string) => {
      setComments(prev => prev.filter(c => c.id !== commentId))
      // Drop the edit selection if the comment being edited disappears (self-delete
      // or a realtime removal), so it doesn't dangle.
      setEditingCommentId(prev => (prev === commentId ? null : prev))
    },
    [setComments]
  )
  const replaceReactions = useCallback(
    (commentId: string, reactions: Record<string, ReactionUser[]>) => {
      setComments(prev => prev.map(c => (c.id === commentId ? { ...c, reactions } : c)))
    },
    [setComments]
  )

  useEmailThreadChannel({ threadId, onMessageAdded: handleMessageAdded })
  useWorkspaceEventsChannel({ workspaceId, onEventAdded: handleEventAdded })
  const { typingUsers } = useEmailThreadCommentsChannel({
    emailThreadId: threadId,
    onCommentCreated: comment => {
      appendComment(comment)
      newMessages.notifyNewItem()
    },
    onCommentUpdated: replaceComment,
    onCommentRemoved: removeComment,
    onReactionToggled: replaceReactions,
  })

  // Decisions ride the workspace_events topic (a second, independent subscription
  // alongside the activity one above). The marker attaches to internal thread
  // comments only — never to EmailMessage items.
  const { decisionsByGid, toggleDecision } = useDecisions({ workspaceId })

  const handleEditComment = useCallback(
    async (commentId: string, content: string, attachmentClaimId: string) => {
      try {
        const updated = await apiFetch<EmailThreadComment>(`/api/email_threads/${threadId}/comments/${commentId}`, {
          method: "PATCH",
          body: JSON.stringify({ content, attachment_claim_id: attachmentClaimId, unfurl_links: true }),
        })
        replaceComment(updated)
      } catch (err) {
        // Re-throw after flashing so the inline editor stays open with the user's
        // edited text (CommentEditor re-enables Save on a rejected save) instead of
        // closing and discarding the edit — matches chat's editMessage.
        showFlash("Couldn't save the comment.")
        throw err
      }
    },
    [threadId, replaceComment]
  )

  const handleDeleteComment = useCallback(
    async (commentId: string) => {
      try {
        await apiFetch(`/api/email_threads/${threadId}/comments/${commentId}`, { method: "DELETE" })
        removeComment(commentId)
      } catch {
        showFlash("Couldn't delete the comment.")
      }
    },
    [threadId, removeComment]
  )

  const handleToggleReaction = useReactionToggle<EmailThreadComment, EmailThreadComment>({
    currentUser: currentUser ? { id: currentUser.id, display_name: currentUser.display_name } : null,
    setItems: setComments,
    buildUrl: (commentId, reactionType) =>
      `/api/email_threads/${threadId}/comments/${commentId}/reactions?reaction_type=${encodeURIComponent(reactionType)}`,
    parseReactions: comment => comment.reactions,
    onError: () => showFlash("Couldn't update the reaction."),
  })

  // Editing a comment and composing a quote-reply are mutually exclusive compose
  // contexts — entering one drops the other, so a lingering reply banner can't
  // silently attach reply_to_id to an unrelated comment.
  const startEditComment = useCallback((commentId: string) => {
    setReplyingTo(null)
    setEditingCommentId(commentId)
  }, [])

  // Slack-style: Up in an empty composer opens the user's most recent own comment
  // for editing. Returns false (leaving the key unconsumed) when there's nothing
  // to edit, so the caret behaves normally.
  const editPreviousComment = useCallback(() => {
    const id = lastOwnItemId(
      comments,
      currentUser?.id ?? null,
      c => c.user?.id,
      c => c.id
    )
    if (!id) return false
    startEditComment(id)
    return true
  }, [comments, currentUser?.id, startEditComment])

  const endEditComment = useCallback(() => setEditingCommentId(null), [])

  useRefocusOnEditClose(
    editingCommentId,
    useCallback(() => commentComposerRef.current?.focus(), [])
  )

  const replyComposer = useReplyComposer({
    threadId,
    // data.draft is refetch-maintained, not patch-maintained: unlike the rest of
    // the envelope, no channel handler patches it, so it's only fresh after a
    // refetch (reconnect / re-arm invalidation), stale while mounted. Safe here
    // because it only seeds the composer bootstrap. Don't read it for realtime UI
    // (e.g. a "draft in progress" badge) without first routing draft mutations
    // through the cache.
    initialDraft: data?.draft ?? null,
    currentUserId: currentUser?.id ?? null,
  })

  // Lifted here (rather than owned inside MailboxActionBar) so the reply composer's
  // send can advance to the same next entry the prev/next arrows point at. "" until
  // the entry loads — the hook no-ops meanwhile.
  const nav = useMailboxEntryNavigation({ mailboxEntryId: mailboxEntry?.id ?? "" })
  // `nav` is a fresh object each render, so resolve through a ref to keep
  // resolveSendDestination referentially stable — an unstable callback would rebind
  // the composer's Cmd+Enter keydown listener on every render.
  const navRef = useRef(nav)
  navRef.current = nav
  // After a successful reply/forward send, advance to the next entry, mirroring the
  // archive/snooze advance in MailboxActionBar: resolve the next href from the
  // pre-drop order, then drop an archived/snoozed entry from the walk. Returns null
  // (no next entry / no navigable list) so the composer falls back to the inbox.
  const resolveSendDestination = useCallback(async ({ archive, snooze, snoozedUntil }: SendOptions) => {
    const current = navRef.current
    const target = await current.resolveNextHref()
    if (archive) current.markCurrentArchived()
    else if (snooze && snoozedUntil) current.markCurrentSnoozed(snoozedUntil)
    return target
  }, [])

  const subject = useDraftSubjectListener(data?.thread.title ?? "")

  const collapsedMessageIds = useMemo(
    () => collapsedMessageIdsFor(timeline, mailboxEntry?.read_at ?? null, mailboxEntry?.is_unread ?? true),
    [timeline, mailboxEntry?.read_at, mailboxEntry?.is_unread]
  )

  const { helpOpen, closeHelp } = useEmailThreadHotkeys()

  // The initial-scroll key and target derive from the FIRST-loaded snapshot, frozen against
  // refetch. Opening the thread marks it read, so a reconnect/event refetch pulls a now-read
  // mailbox_entry; deriving from the live `data` would flip the read-state, change the key,
  // and re-fire the "initial" scroll — yanking a mid-read user to the top of the email
  // (#8838). The frozen cursor also feeds the unread divider so it stays put as the thread is
  // marked read. Live read-state still drives collapse and the action bar.
  const { scrollKey, messageScrollTargetId, commentScrollTargetId, readCursor, hasCollapsedGroup } =
    useInitialScrollTarget(threadId, data, currentUser?.id ?? null)

  // The first item that renders expanded on load — the earliest unread item, or the
  // always-expanded newest message on a fully-read thread. In every branch of
  // useInitialScrollTarget that's exactly whichever scroll target is set, so the read run
  // before it is what the collapsed group compacts (see collapsedGroup.ts).
  const collapseBoundaryId = messageScrollTargetId ?? commentScrollTargetId

  // The comment unread divider marks the first comment newer than the last read. The cursor
  // comes from the frozen load snapshot so it stays put as the thread is marked read; the
  // count runs over live comments so replies arriving mid-session join the tally below it.
  const unreadCommentList = useMemo(
    () =>
      readCursor ? unreadComments(comments, readCursor.readAt, readCursor.isUnread, currentUser?.id ?? null) : [],
    [readCursor, comments, currentUser?.id]
  )
  const firstUnreadCommentId = unreadCommentList[0]?.id ?? null
  const unreadCommentCount = unreadCommentList.length

  // The target message's scroll-mt (see EmailMessage) clears the sticky header so
  // the top-aligned message isn't hidden behind it. Scroll rationale lives in the hook.
  const registerScrollTarget = useInitialThreadScroll(scrollKey)
  useScrollToUnreadComment(hasCollapsedGroup ? null : commentScrollTargetId, scrollKey)

  const draftScrollKey =
    replyComposer.composerProps?.focusBody && replyComposer.composerProps.draftMessageId
      ? replyComposer.composerProps.draftMessageId
      : null
  useScrollToDraft({ composerRef, scrollKey: draftScrollKey })

  // Deep-link from a search result (or notification) to a specific comment via
  // the `#comment-<id>` hash, once the comments have loaded. scrollToComment
  // also backs click-to-quote — a live quote and a hash link scroll identically.
  const { highlightedId: highlightedCommentId, scrollToComment } = useScrollToHashComment(comments.length > 0)

  // Quote-reply: open the composer's banner for a comment and focus the composer.
  // Cancels any open inline edit (see startEditComment) so the two don't coexist.
  const startReply = useCallback((preview: ReplyPreview) => {
    setEditingCommentId(null)
    setReplyingTo(preview)
    commentComposerRef.current?.focus()
  }, [])
  const clearReply = useCallback(() => setReplyingTo(null), [])

  const submitReply = useCallback(
    async (url: string, replyType: "reply" | "reply_all" | "forward", replaceExisting: boolean) => {
      try {
        const body =
          replyType === "forward"
            ? JSON.stringify({ replace_existing: replaceExisting })
            : JSON.stringify({ reply_type: replyType, replace_existing: replaceExisting })
        await apiFetch(url, { method: "POST", body })
        replyComposer.mountAfterAction()
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          setPendingReply({ url, replyType })
          return
        }
        showFlash("Couldn't start the reply.")
      }
    },
    [replyComposer]
  )

  const handleReply = useCallback(
    (messageId: string) => {
      const msg = timeline.find(i => i.type === "message" && i.message.id === messageId)
      if (msg?.type === "message") void submitReply(msg.message.reply_url, "reply", false)
    },
    [timeline, submitReply]
  )
  const handleReplyAll = useCallback(
    (messageId: string) => {
      const msg = timeline.find(i => i.type === "message" && i.message.id === messageId)
      if (msg?.type === "message") void submitReply(msg.message.reply_url, "reply_all", false)
    },
    [timeline, submitReply]
  )
  const handleForward = useCallback(
    (messageId: string) => {
      const msg = timeline.find(i => i.type === "message" && i.message.id === messageId)
      if (msg?.type === "message") void submitReply(msg.message.forward_url, "forward", false)
    },
    [timeline, submitReply]
  )

  const confirmReplace = useCallback(() => {
    if (!pendingReply) return
    const { url, replyType } = pendingReply
    setPendingReply(null)
    void submitReply(url, replyType, true)
  }, [pendingReply, submitReply])

  const handleAiToggle = useCallback(
    async (excludeFromAi: boolean) => {
      if (!mailboxEntry) return
      const url = `/api/email_threads/${threadId}/${excludeFromAi ? "exclude_from_ai" : "include_in_ai"}`
      // Optimistic: flip the flag now, revert to the prior value (the button
      // toggled the current one, so that's !excludeFromAi) if the POST fails.
      setMailboxEntry(prev => ({ ...prev, is_ai_excluded: excludeFromAi }))
      try {
        await apiFetch(url, { method: "POST" })
      } catch {
        setMailboxEntry(prev => ({ ...prev, is_ai_excluded: !excludeFromAi }))
        showFlash("Couldn't update AI inclusion.")
      }
    },
    [mailboxEntry, threadId, setMailboxEntry]
  )

  // A same-org non-collaborator gets 403 + request_access_url from the API (the
  // server-side page redirect is gone now the shell serves unconditionally). Offer
  // the request-access CTA rather than a dead-end error — the documents precedent.
  const requestAccessUrl = accessDeniedUrl(query.error)
  if (requestAccessUrl) {
    return <RequestDocumentAccess requestAccessUrl={requestAccessUrl} resourceLabel="thread" />
  }
  if (query.isError) {
    return <div className="p-4 text-error">Couldn't load this thread. Please refresh.</div>
  }
  if (!data || !mailboxEntry) {
    return <EmailThreadSkeleton />
  }

  // Re-sourced client-side from the route's return_to (the API no longer computes
  // it). Defaults to the inbox — the server's mailbox_index fallback.
  const back = emailThreadBackNavigation(returnTo)

  const isCreator = currentUser?.id === data.thread.creator.id
  // The sticky toolbar holds the AI toggle (creator-only) in the joined action
  // cluster, followed by the "shared with" collaborators + "assigned to" picker
  // flowing left on the same row. Hidden on mobile to keep the row from
  // overflowing — it's a low-frequency creator control.
  const headerLeftSlot =
    isCreator && !isMobile ? (
      <Tooltip
        content={mailboxEntry.is_ai_excluded ? "Include in AI processing" : "Exclude from AI processing"}
        placement="bottom"
      >
        <button
          type="button"
          onClick={() => void handleAiToggle(!mailboxEntry.is_ai_excluded)}
          aria-label={mailboxEntry.is_ai_excluded ? "Include in AI processing" : "Exclude from AI processing"}
          className={MAILBOX_ACTION_SEGMENT_CLASS}
        >
          <span className="material-symbols-outlined text-lg">
            {mailboxEntry.is_ai_excluded ? "blur_off" : "blur_on"}
          </span>
        </button>
      </Tooltip>
    ) : null

  const headerRightSlot = (
    <>
      <WorkspaceCollaborators workspaceId={workspaceId} />
      <WorkspaceAssignment workspaceId={workspaceId} />
    </>
  )

  return (
    <div ref={rootRef} id="email-thread" data-testid="email-thread" className="-mb-12 flex flex-col">
      <EmailThreadHeader
        actionBar={
          <MailboxActionBar
            state={buildMailboxState(mailboxEntry)}
            actionUrls={mailboxActionUrls(mailboxEntry.id)}
            mailboxEntryId={mailboxEntry.id}
            navigation={nav}
            back={back}
            navLink
            leftSlot={headerLeftSlot}
            trailingSlot={headerRightSlot}
            onStateChange={(next: MailboxState) =>
              setMailboxEntry(prev => ({
                ...prev,
                is_unread: next.isUnread,
                // Mirror the server: explicit mark-unread clears read_at so the whole
                // thread re-expands. No channel broadcast fires for this, so this
                // optimistic update is what drives the re-expand.
                read_at: next.isUnread ? null : prev.read_at,
                is_archived: next.isArchived,
                is_snoozed: next.isSnoozed,
                snoozed_until: next.snoozedUntil,
              }))
            }
          />
        }
      />

      <div className="w-full max-w-4xl mx-auto flex flex-col flex-1">
        {/* Thread content stays narrow; the comment composer below spans the wider shell.
            flex-1 lets it grow so the composer is pushed to the viewport bottom on short threads. */}
        <div className="w-full max-w-3xl mx-auto flex flex-col flex-1">
          <EmailThreadTitle thread={data.thread} mailboxEntry={mailboxEntry} subject={subject} />
          <div className="grid gap-4">
            <div className="grid gap-4 px-2">
              <Timeline
                items={timeline}
                comments={comments}
                collapsedMessageIds={collapsedMessageIds}
                canReply={data.thread.can_reply}
                isSuperuser={currentUser?.is_superuser ?? false}
                currentUserEmail={currentUser?.email ?? null}
                currentUserId={currentUser?.id ?? null}
                workspaceId={workspaceId}
                decisionsByGid={decisionsByGid}
                highlightedCommentId={highlightedCommentId}
                editingCommentId={editingCommentId}
                onStartEditComment={startEditComment}
                onEndEditComment={endEditComment}
                scrollTargetId={hasCollapsedGroup ? null : messageScrollTargetId}
                scrollTargetRef={registerScrollTarget}
                collapseBoundaryId={collapseBoundaryId}
                firstUnreadCommentId={firstUnreadCommentId}
                unreadCommentCount={unreadCommentCount}
                onReply={handleReply}
                onReplyAll={handleReplyAll}
                onForward={handleForward}
                onEditComment={handleEditComment}
                onDeleteComment={handleDeleteComment}
                onToggleReaction={handleToggleReaction}
                onToggleDecision={toggleDecision}
                onReplyToComment={startReply}
                onScrollToComment={scrollToComment}
              />
            </div>
            <div className="px-6">
              <TypingIndicator users={typingUsers} />
            </div>
            {replyComposer.composerProps && (
              <div className="px-2" ref={composerRef}>
                <EmailComposer {...replyComposer.composerProps} resolveSendDestination={resolveSendDestination} />
              </div>
            )}

            {newMessages.hasNewMessages && (
              <div className="fixed bottom-[calc(5rem+var(--safe-area-inset-bottom))] left-1/2 transform -translate-x-1/2 z-20">
                <button
                  type="button"
                  onClick={newMessages.scrollToNewMessage}
                  className="btn btn-primary btn-sm rounded-full shadow-lg flex items-center gap-2"
                >
                  <span className="material-symbols-outlined text-sm">keyboard_arrow_down</span>
                  <span>New messages</span>
                </button>
              </div>
            )}
          </div>
        </div>

        <div
          className={
            isMobile
              ? "sticky bottom-[var(--mobile-nav-offset)] z-20 mt-4 -mx-2"
              : "sticky bottom-0 z-20 mt-4 max-w-composer mx-auto w-full pb-[var(--safe-area-inset-bottom)] pl-[var(--safe-area-inset-left)] pr-[var(--safe-area-inset-right)]"
          }
        >
          <EmailThreadCommentForm
            ref={commentComposerRef}
            workspaceId={workspaceId}
            threadId={threadId}
            onEditPrevious={editPreviousComment}
            replyingTo={replyingTo}
            onClearReply={clearReply}
            onSent={comment => {
              appendComment(comment)
              setReplyingTo(null)
              newMessages.scrollToNewMessage()
            }}
          />
          {!isMobile && (
            <div className="w-full h-4 bg-base-100">{/* Scroll-fade behind the sticky comment form. */}</div>
          )}
        </div>
      </div>

      <HelpDialog open={helpOpen} onClose={closeHelp} />

      {pendingReply && (
        <DraftConflictDialog
          open
          replyType={pendingReply.replyType}
          onConfirm={confirmReplace}
          onCancel={() => setPendingReply(null)}
        />
      )}
    </div>
  )
}
