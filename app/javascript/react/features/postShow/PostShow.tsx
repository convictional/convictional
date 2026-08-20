import { useQuery, useQueryClient } from "@tanstack/react-query"
import { getRouteApi, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { ApiError } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDecisions } from "~/react/shared/hooks/useDecisions"
import { useDisableDocumentScrollAnchor } from "~/react/shared/hooks/useDisableDocumentScrollAnchor"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useMailboxEntryReadTracking } from "~/react/shared/hooks/useMailboxEntryReadTracking"
import { findCommentElement, useScrollToHashComment } from "~/react/shared/hooks/useScrollToHashComment"
import { postBackNavigation, postNavigationSearch } from "~/react/shared/postNavigation"
import type { ReactionType } from "~/react/shared/reactions"
import type { BackNavigation, Post, PostComment, PostMailboxEntry, PostShowResponse } from "~/react/shared/types"

import type { CommentThreadProps } from "./commentThread"
import { AddCommentBar } from "./components/AddCommentBar"
import { CommentList } from "./components/CommentList"
import { PostBody } from "./components/PostBody"
import { PostShowHeader } from "./components/PostShowHeader"
import { WhatsNewPanel } from "./components/WhatsNewPanel"
import { useNewCommentsIndicator } from "./hooks/useNewCommentsIndicator"
import { usePostComments } from "./hooks/usePostComments"
import { PostShowSkeleton } from "./PostShowSkeleton"
import { postQueryKey, postQueryOptions } from "./queries"
import { computeWhatsNew } from "./whatsNew"

// The route id carries the pathless shell parent prefix (shellRoute has id
// "shell"), so the typed accessor is addressed as "/shell/posts/$postId".
const routeApi = getRouteApi("/shell/posts/$postId")

export function PostShow() {
  const { postId } = routeApi.useParams()
  const { return_to: returnTo, mailbox_entry_id: mailboxEntryId } = routeApi.useSearch()
  const navigate = useNavigate()

  const detail = useQuery(postQueryOptions(postId, mailboxEntryId))
  const data = detail.data

  useDocumentTitle(data?.post.title ?? "Post")

  // Drafts 404 at the show endpoint (GET /api/posts/{id} excludes them) — they
  // live in the editor, so client-route there, preserving return_to + mailbox
  // context. replace() keeps the show URL out of history so Back doesn't bounce
  // through it. Holding the skeleton (below) through the navigation keeps the
  // error state from flashing. The editor tells published-vs-nonexistent apart
  // (a genuine 404 lands on its error state), so this can't ping-pong back — see
  // PostDraftEditor.
  const isDraftRedirect = detail.error instanceof ApiError && detail.error.status === 404
  useEffect(() => {
    if (isDraftRedirect) {
      void navigate({
        to: "/posts/$postId/edit",
        params: { postId },
        search: postNavigationSearch(returnTo, mailboxEntryId),
        replace: true,
      })
    }
  }, [isDraftRedirect, postId, returnTo, mailboxEntryId, navigate])

  const back = postBackNavigation(returnTo, mailboxEntryId)

  // Hold the skeleton through the draft redirect so the error state never flashes.
  if (isDraftRedirect) return <PostShowSkeleton />
  if (detail.isError) return <div className="p-4 text-error">Couldn't load this post. Please refresh.</div>
  if (!data) {
    return <PostShowSkeleton />
  }

  // Key on postId so navigating between posts remounts the content — the detail
  // query is keyed per post, but PostShowContent also holds per-post local state
  // (the one-shot visit record, what's-new dismissal) that must reset per post.
  // This replaces the old reset-on-postId-change effect, which cleared that state
  // by forcing a remount through a null-data gap.
  return <PostShowContent key={postId} postId={postId} data={data} back={back} />
}

function PostShowContent({ postId, data, back }: { postId: string; data: PostShowResponse; back: BackNavigation }) {
  const { user } = useCurrentUser()
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
  const currentUserId = user?.id ?? ""
  const rootRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLDivElement>(null)

  // The post entity and its mailbox entry live in the detail-query cache; reads
  // come off the live `data` prop and edit-in-place/pin/mailbox mutations patch
  // the cache so it stays the single source of truth (replaces usePostShowState).
  const post = data.post
  const mailboxEntry = data.mailbox_entry
  const updatePost = useCallback(
    (patch: Partial<Post>) =>
      queryClient.setQueryData<PostShowResponse>(postQueryKey(postId), old =>
        old ? { ...old, post: { ...old.post, ...patch } } : old
      ),
    [queryClient, postId]
  )
  const setMailboxEntry = useCallback(
    (entry: PostMailboxEntry) =>
      queryClient.setQueryData<PostShowResponse>(postQueryKey(postId), old =>
        old ? { ...old, mailbox_entry: entry } : old
      ),
    [queryClient, postId]
  )

  // Freeze last_visit_at at first load, before this island records the visit.
  // The detail query can refetch (remount, reconnect) and return a post-visit
  // last_visit_at, which would collapse what's-new to empty — so what's-new is
  // always computed against this frozen pre-visit value, never the live one.
  const [lastVisitAt] = useState(data.last_visit_at)

  // The comment composer is fixed to the bottom and grows as you type. Reserve
  // its live height as bottom padding so the last comments can always be scrolled
  // clear of it instead of being trapped behind the expanded composer. Write the
  // height to a CSS variable on the root rather than React state so the composer
  // growing on every keystroke doesn't re-render the whole comment tree.
  useEffect(() => {
    const el = composerRef.current
    const root = rootRef.current
    if (!el || !root) return
    const measure = () => root.style.setProperty("--composer-reserve", `${el.offsetHeight}px`)
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    measure()
    return () => observer.disconnect()
  }, [])

  useDisableDocumentScrollAnchor()

  // No markReadOnMount: MailboxActionBar's useAutoMarkRead already marks the post
  // read after open, so this hook only needs to catch comments arriving live.
  const readTracking = useMailboxEntryReadTracking({
    mailboxEntryId: mailboxEntry?.id ?? null,
    currentUserId,
    enabled: Boolean(currentUserId),
    flushOnUnmount: "when-pending",
  })
  const { highlightedId, scrollToComment } = useScrollToHashComment()
  const newComments = useNewCommentsIndicator({ workspaceId: post.workspace_id })
  const [whatsNewDismissed, setWhatsNewDismissed] = useState(false)

  // Record the visit once, now that the detail query has resolved (this component
  // only mounts with `data` in hand). `lastVisitAt` is frozen above, so "what's
  // new" is computed against the pre-arrival visit before this bumps it. The
  // island is the only thing that records the visit (the page shell records none
  // on load), so nothing bumps last_visit_at ahead of that computation.
  // trackedVisitRef keeps this to one record per mount, matching emailThreadShow
  // and goalShow (and avoiding a duplicate POST under StrictMode's dev remount).
  const recordVisit = newComments.recordVisit
  const trackedVisitRef = useRef(false)
  useEffect(() => {
    if (trackedVisitRef.current) return
    trackedVisitRef.current = true
    recordVisit()
  }, [recordVisit])

  const comments = usePostComments({
    postId,
    currentUserId,
    initial: data.top_level_comments,
    initialOriginal: data.original_comment,
    // Defer one frame so the just-inserted comment has rendered before we resolve
    // its node — lets the pill point its arrow and scroll precisely to it.
    onRemoteCreate: comment => {
      readTracking.notifyIncoming(comment.user.id)
      requestAnimationFrame(() => newComments.notifyNewComment(findCommentElement(comment.id)))
    },
  })

  const decisions = useDecisions({
    workspaceId: post.workspace_id,
  })

  // A decision's comment_gid is gid://convictional/PostComment/<id>; the rendered
  // comment is keyed by that trailing id, so jump by parsing it out.
  const scrollToDecision = useCallback(
    (commentGid: string) => scrollToComment(commentGid.split("/").pop() ?? ""),
    [scrollToComment]
  )

  // Resolve any comment by gid (original + top-level + replies) so what's-new can
  // attach each new decision to its decided comment and reflect live edits.
  const commentsByGid = useMemo<Map<string, PostComment>>(() => {
    const map = new Map<string, PostComment>()
    if (comments.original) map.set(comments.original.global_id, comments.original)
    for (const comment of comments.topLevel) {
      map.set(comment.global_id, comment)
      for (const reply of comment.replies) map.set(reply.global_id, reply)
    }
    return map
  }, [comments.original, comments.topLevel])

  // "New since last visit" summary, computed once. The panel hides it once
  // dismissed; the inline New badge ignores dismissal, so both derive from the
  // same result.
  const whatsNewSummary = useMemo(
    () => computeWhatsNew(comments.topLevel, decisions.decisions, commentsByGid, lastVisitAt, currentUserId),
    [comments.topLevel, decisions.decisions, commentsByGid, lastVisitAt, currentUserId]
  )
  const whatsNew = whatsNewDismissed ? null : whatsNewSummary
  const newCommentIds = useMemo(
    () => new Set(whatsNewSummary?.groups.flatMap(g => g.comments.map(c => c.id)) ?? []),
    [whatsNewSummary]
  )

  const ctx: CommentThreadProps = {
    workspaceId: post.workspace_id,
    currentUserId,
    decisionsByGid: decisions.decisionsByGid,
    toggleDecision: decisions.toggleDecision,
    newCommentIds,
    highlightedId,
    createComment: comments.createComment,
    editComment: comments.editComment,
    deleteComment: comments.deleteComment,
    toggleReaction: comments.toggleReaction,
  }

  const scrollCommentsToBottom = useCallback(() => {
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" })
  }, [])

  return (
    <div
      ref={rootRef}
      id="post"
      className="max-w-4xl w-full mx-auto space-y-4 px-2"
      style={{
        paddingBottom: `calc(${
          isMobile ? "var(--mobile-nav-offset)" : "var(--safe-area-inset-bottom)"
        } + var(--composer-reserve, 0px) + 1rem)`,
      }}
    >
      <PostShowHeader
        post={post}
        mailboxEntry={mailboxEntry}
        back={back}
        onPinChange={updatePost}
        onMailboxStateChange={setMailboxEntry}
      />

      {/* The pinned/announcement badge floats above the post card (-top-3); the
          extra top gap drops it clear of the sticky-header fade band so its top
          isn't veiled. */}
      <div className={`max-w-3xl mx-auto space-y-4${post.is_pinned || post.is_announcement ? " pt-3" : ""}`}>
        <PostBody
          post={post}
          originalComment={comments.original}
          decisions={decisions.decisions}
          decisionsByGid={decisions.decisionsByGid}
          toggleDecision={decisions.toggleDecision}
          currentUserId={currentUserId}
          onSave={(updated, content) => {
            updatePost(updated)
            comments.setOriginalContent(content)
          }}
          onToggleReaction={type => {
            if (comments.original) comments.toggleReaction(comments.original.id, type as ReactionType)
          }}
          onJumpToDecision={scrollToDecision}
        />

        {whatsNew && (
          <WhatsNewPanel whatsNew={whatsNew} onJump={scrollToComment} onDismiss={() => setWhatsNewDismissed(true)} />
        )}

        <div className="mx-2 sm:mx-8">
          <CommentList comments={comments.topLevel} ctx={ctx} />
        </div>
      </div>

      {newComments.hasNew && (
        <div className="fixed bottom-[calc(5rem+var(--safe-area-inset-bottom))] left-1/2 transform -translate-x-1/2 z-20">
          <button
            type="button"
            onClick={newComments.scrollToNew}
            className="btn btn-primary btn-sm rounded-full shadow-lg flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-sm">
              {newComments.isAbove ? "keyboard_arrow_up" : "keyboard_arrow_down"}
            </span>
            <span>New comments</span>
          </button>
        </div>
      )}

      {/* Pinned above the mobile bottom nav; on desktop there's no nav, so it
          sits at the safe-area edge. The 1rem inset matches the root's px-2 on
          both sides so the composer's edges line up with the post content, and
          max-w-4xl keeps it the same width as that content column. */}
      <div
        ref={composerRef}
        className={`fixed z-20 left-1/2 -translate-x-1/2 pl-[var(--safe-area-inset-left)] pr-[var(--safe-area-inset-right)] w-[calc(100%-1rem)] max-w-4xl ${
          isMobile ? "bottom-[var(--mobile-nav-offset)]" : "bottom-[var(--safe-area-inset-bottom)]"
        }`}
      >
        <AddCommentBar
          workspaceId={post.workspace_id}
          onSubmit={(content, attachmentClaimId, unfurlLinks) =>
            comments.createComment(content, { attachmentClaimId, unfurlLinks })
          }
          onSent={scrollCommentsToBottom}
        />
      </div>
    </div>
  )
}
