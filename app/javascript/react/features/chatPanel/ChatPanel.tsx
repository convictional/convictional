import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type UIEvent } from "react"

import { ChatComposerEditor, type ChatEditorHandle } from "~/react/composites/chat/ChatComposerEditor"
import { ChatHeaderAvatar } from "~/react/composites/chat/ChatHeaderAvatar"
import { ComposeReplyPreview } from "~/react/composites/chat/ComposeReplyPreview"
import { InteractiveMessageBubble } from "~/react/composites/chat/InteractiveMessageBubble"
import { JumpToLatestPill } from "~/react/composites/chat/JumpToLatestPill"
import { LinkPreviewCard } from "~/react/composites/chat/LinkPreviewCard"
import { replyContentPreview } from "~/react/composites/chat/replyPreview"
import { TypingIndicator } from "~/react/composites/chat/TypingIndicator"
import { GifPicker, type KlipyGif } from "~/react/composites/editor/components/GifPicker"
import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDropzone } from "~/react/shared/hooks/useDropzone"
import { type MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import { useRefocusOnEditClose } from "~/react/shared/hooks/useRefocusOnEditClose"
import { useScrollToReply } from "~/react/shared/hooks/useScrollToReply"
import { lastOwnItemId } from "~/react/shared/lastOwnItem"
import { isContinuation } from "~/react/shared/messageGrouping"
import type { ChatMessage, ChatType, ReplyPreview } from "~/react/shared/types"
import { DropzoneOverlay } from "~/react/ui/DropzoneOverlay"
import { useChatPanelState } from "./useChatPanelState"

// Fire forward pagination once the user scrolls within this many pixels of the bottom.
const LOAD_NEWER_LOOKAHEAD_PX = 50

function MessageList({
  messages,
  loading,
  loadingMore,
  hasMore,
  currentUserId,
  editingMessageId,
  chatType,
  uploadUrl,
  mentionableUsers,
  mentionsEnabled,
  klipyApiKey,
  onLoadMore,
  onLoadNewer,
  hasNewer,
  onScrollTo,
  scrollingToId,
  scrollingToReplyRef,
  atTail,
  onJumpToLatest,
  onReply,
  onEdit,
  onCancelEdit,
  onSaveEdit,
  onDelete,
  onReact,
}: {
  messages: ChatMessage[]
  loading: boolean
  loadingMore: boolean
  hasMore: boolean
  currentUserId: string | null
  editingMessageId: string | null
  chatType: ChatType
  uploadUrl: string | null
  mentionableUsers: MentionUser[]
  mentionsEnabled?: boolean
  klipyApiKey: string | null
  onLoadMore: () => void
  onLoadNewer: () => void
  hasNewer: boolean
  onScrollTo: (id: string) => void
  scrollingToId: string | null
  scrollingToReplyRef: React.RefObject<boolean>
  // Loaded bottom is the live tail. When false the list is a not-caught-up
  // historical window (quote-reply jump): auto-scroll is gated off, forward
  // pagination closes the gap, and the pill offers a fast-skip to the tail.
  atTail: boolean
  onJumpToLatest: () => void
  onReply: (reply: ReplyPreview) => void
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
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const lastMessageId = messages[messages.length - 1]?.id
  // Hold scroll position when load-more prepends older messages. Document scroll
  // anchoring is disabled, so a prepend at scrollTop 0 would otherwise pin the
  // user to the oldest newly-loaded message. Holds the first message id captured
  // when a load-more is triggered; compensation runs only once that id actually
  // changes (a page was really prepended). Anchoring on the id rather than a
  // boolean means a failed load — which never changes `messages` — can't leave a
  // stale flag that misfires on the next incoming message.
  const prependAnchorRef = useRef<string | null>(null)
  const prevScrollHeightRef = useRef(0)

  // Auto-scroll to the newest message — but not while not at the tail, where
  // pinning to a historical window's bottom would yank the user out of the jump.
  useEffect(() => {
    if (!atTail) return
    endRef.current?.scrollIntoView({ behavior: "instant" })
  }, [lastMessageId, atTail])

  // Auto-load more if the container isn't scrollable yet (content doesn't overflow)
  useEffect(() => {
    const el = containerRef.current
    if (!el || !hasMore || loadingMore || scrollingToReplyRef.current) return
    if (el.scrollHeight <= el.clientHeight) {
      // No scroll position to preserve here (everything fits), and scrollHeight
      // is clamped to clientHeight so the delta would be wrong — don't flag it.
      onLoadMore()
    }
  }, [messages, hasMore, loadingMore, onLoadMore, scrollingToReplyRef])

  // Restore scroll position before paint after a prepend grows the container.
  // Shift scrollTop by the height delta so the visible message stays put; only
  // the scroll-up path sets the flag (scrollToReply ends with its own scroll).
  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const anchor = prependAnchorRef.current
    if (anchor !== null && messages[0]?.id !== anchor) {
      prependAnchorRef.current = null
      const delta = el.scrollHeight - prevScrollHeightRef.current
      if (delta > 0) el.scrollTop += delta
    }
    prevScrollHeightRef.current = el.scrollHeight
  }, [messages])

  // Load older when scrolled to top; load newer (forward pagination, while not
  // at the tail) when scrolled to the bottom — the mirror of the top case.
  function handleScroll(e: UIEvent<HTMLDivElement>) {
    const el = e.currentTarget
    if (el.scrollTop === 0 && hasMore && !loadingMore && !scrollingToReplyRef.current) {
      prependAnchorRef.current = messages[0]?.id ?? null
      onLoadMore()
    }
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    if (!atTail && hasNewer && !scrollingToReplyRef.current && distanceFromBottom < LOAD_NEWER_LOOKAHEAD_PX) {
      onLoadNewer()
    }
  }

  if (loading && messages.length === 0) {
    return (
      <div className="flex-1 min-h-60 flex items-center justify-center text-base-content/40 text-sm bg-base-100">
        Loading...
      </div>
    )
  }

  if (messages.length === 0) {
    return (
      <div className="flex-1 min-h-60 flex items-center justify-center text-base-content/40 text-sm px-4 text-center bg-base-100">
        No messages yet. Say hello!
      </div>
    )
  }

  return (
    <div className="relative flex-1 min-h-0 flex flex-col">
      <div ref={containerRef} onScroll={handleScroll} className="flex-1 min-h-0 overflow-y-auto px-3 py-2 bg-base-100">
        {loadingMore && <div className="text-center text-xs text-base-content/40 py-1">Loading...</div>}
        {currentUserId &&
          messages.map((msg, i) => {
            const grouped = isContinuation(messages[i - 1], msg)
            return (
              <InteractiveMessageBubble
                key={msg.id}
                message={msg}
                className={i === 0 ? "" : grouped ? "mt-0.5" : "mt-2"}
                currentUserId={currentUserId}
                isGrouped={grouped}
                isEditing={editingMessageId === msg.id}
                isCompact
                chatType={chatType}
                uploadUrl={uploadUrl}
                mentionableUsers={mentionableUsers}
                mentionsEnabled={mentionsEnabled}
                klipyApiKey={klipyApiKey}
                onScrollTo={onScrollTo}
                scrollingToId={scrollingToId}
                onEdit={() => onEdit(msg.id)}
                onCancelEdit={onCancelEdit}
                onSaveEdit={onSaveEdit}
                onDelete={() => onDelete(msg.id)}
                onReact={onReact}
                onReply={() =>
                  onReply({
                    id: msg.id,
                    user_name: msg.user.display_name,
                    content_preview: replyContentPreview(msg.content),
                    is_deleted: false,
                  })
                }
              />
            )
          })}
        <div ref={endRef} />
      </div>
      {/* Offer a fast-skip back to the live tail while not at it (a window jump);
          forward pagination handles the gradual catch-up if the user scrolls. */}
      {!atTail && (
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-10">
          <JumpToLatestPill onClick={onJumpToLatest} label="Jump to latest" variant="latest" />
        </div>
      )}
    </div>
  )
}

export function ChatPanel() {
  const klipyApiKey = useCurrentUser().clientConfig?.klipy_api_key ?? null
  const {
    panelState,
    messages,
    loading,
    loadingMore,
    hasMore,
    sending,
    sendError,
    replyTo,
    sendMessage,
    editMessage,
    deleteMessage,
    toggleReaction,
    editingMessageId,
    setEditingMessageId,
    cancelEdit,
    claimId,
    uploadUrl,
    supportsMentions,
    currentUserId,
    loadMore,
    loadNewer,
    hasNewer,
    jumpToMessage,
    jumpToLatest,
    atTail,
    minimize,
    restore,
    close,
    retryLoad,
    setDraftContent,
    setReplyTo,
    composePreview,
    dismissComposePreview,
    typingUsers,
    initialDraft,
  } = useChatPanelState()

  const { scrollToReply, scrollingToReplyRef, scrollingToId } = useScrollToReply(jumpToMessage)

  // Mention candidates: the chat's collaborators, including yourself — mentioning
  // yourself works like mentioning anyone else. Built straight from the collaborator
  // list we hold, not the org-members store, so non-org-member collaborators stay mentionable.
  const mentionableUsers = useMemo<MentionUser[]>(() => {
    const source = panelState?.display.collaborators ?? []
    return source.map(c => ({ id: c.user.id, display_name: c.user.display_name, is_collaborator: true }))
  }, [panelState?.display.collaborators])

  const editorRef = useRef<ChatEditorHandle>(null)
  useEffect(() => {
    if (replyTo) editorRef.current?.focus()
  }, [replyTo])

  useRefocusOnEditClose(
    editingMessageId,
    useCallback(() => editorRef.current?.focus(), [])
  )

  const handleDroppedFiles = useCallback((files: File[]) => {
    editorRef.current?.uploadFiles(files)
  }, [])
  const { isDragOver, ref: dropzoneRef } = useDropzone({
    onFiles: handleDroppedFiles,
    enabled: !!uploadUrl && !panelState?.minimized,
  })

  // After a send, claimId rotates and the editor remounts (key=claimId).
  // Auto-focus the fresh view on every subsequent mount so users can fire
  // back-to-back messages. Skip the very first mount so a panel restored
  // from sessionStorage on page load doesn't steal focus from the page.
  const [initialClaimId] = useState(claimId)
  const autoFocus = claimId !== initialClaimId

  const handleSend = useCallback((content: string) => sendMessage(content, claimId), [sendMessage, claimId])

  const editPreviousMessage = useCallback(() => {
    const id = lastOwnItemId(
      messages,
      currentUserId,
      m => m.user.id,
      m => m.id
    )
    if (!id) return false
    setEditingMessageId(id)
    return true
  }, [messages, currentUserId, setEditingMessageId])

  const handleSelectGif = useCallback((gif: KlipyGif) => {
    editorRef.current?.insertImage(gif.content_url, gif.title)
  }, [])

  // Boost the "open full chat" anchor so navigating to /chats/:id stays soft.
  const rootRef = useRef<HTMLDivElement>(null)
  useBoostIslandLinks(rootRef, [panelState?.chatId, panelState?.minimized])

  if (!panelState) return null

  const { display, minimized, chatId, loadFailed } = panelState

  // Minimized state — compact header bar
  if (minimized) {
    return (
      <div
        className="fixed bottom-[max(1rem,var(--safe-area-inset-bottom))] right-4 z-40 max-w-72 floating-card !p-0 cursor-pointer"
        onClick={restore}
      >
        <div className="flex items-center gap-2 px-3 py-2">
          <ChatHeaderAvatar
            type={display.type}
            collaborators={display.collaborators}
            currentUserId={currentUserId}
            size="small"
          />
          <span className="text-sm font-medium truncate flex-1">{display.title}</span>
          <button
            type="button"
            onClick={e => {
              e.stopPropagation()
              close()
            }}
            className="text-base-content/40 hover:text-base-content/70"
          >
            <span className="material-symbols-outlined text-lg">close</span>
          </button>
        </div>
      </div>
    )
  }

  // Full panel
  return (
    <div
      ref={dropzoneRef}
      className="fixed bottom-[max(1rem,var(--safe-area-inset-bottom))] right-4 z-40 w-96 max-h-[min(480px,calc(100vh-2rem))] floating-card !p-0 flex flex-col overflow-hidden"
    >
      {isDragOver && <DropzoneOverlay centerOnScreen />}
      {/* Header */}
      <div ref={rootRef} className="flex items-center gap-2 px-3 py-2 border-b border-base-400">
        <ChatHeaderAvatar
          type={display.type}
          collaborators={display.collaborators}
          currentUserId={currentUserId}
          size="medium"
        />
        <span className="text-sm font-medium truncate flex-1">{display.title}</span>
        <div className="flex items-center gap-1.5">
          {chatId && (
            <a
              href={`/chats/${chatId}`}
              onClick={close}
              className="cursor-pointer text-base-content/40 hover:text-base-content/70"
              title="Open full chat"
            >
              <span className="material-symbols-outlined text-lg">open_in_new</span>
            </a>
          )}
          <button
            type="button"
            onClick={minimize}
            className="cursor-pointer text-base-content/40 hover:text-base-content/70"
            title="Minimize"
          >
            <span className="material-symbols-outlined text-lg">minimize</span>
          </button>
          <button
            type="button"
            onClick={close}
            className="cursor-pointer text-base-content/40 hover:text-base-content/70"
            title="Close"
          >
            <span className="material-symbols-outlined text-lg">close</span>
          </button>
        </div>
      </div>

      {loadFailed && (
        <div className="flex items-center gap-2 px-3 py-2 bg-warning/10 border-b border-base-400 text-xs">
          <span className="flex-1">Couldn't load conversation.</span>
          <button type="button" onClick={retryLoad} className="btn btn-xs btn-ghost">
            Retry
          </button>
        </div>
      )}

      {/* Messages */}
      <MessageList
        messages={messages}
        loading={loading}
        loadingMore={loadingMore}
        hasMore={hasMore}
        currentUserId={currentUserId}
        editingMessageId={editingMessageId}
        chatType={display.type}
        uploadUrl={uploadUrl}
        mentionableUsers={mentionableUsers}
        mentionsEnabled={supportsMentions}
        klipyApiKey={klipyApiKey}
        onLoadMore={loadMore}
        onLoadNewer={loadNewer}
        hasNewer={hasNewer}
        onScrollTo={scrollToReply}
        scrollingToId={scrollingToId}
        scrollingToReplyRef={scrollingToReplyRef}
        atTail={atTail}
        onJumpToLatest={jumpToLatest}
        onReply={setReplyTo}
        onEdit={setEditingMessageId}
        onCancelEdit={cancelEdit}
        onSaveEdit={editMessage}
        onDelete={deleteMessage}
        onReact={toggleReaction}
      />

      <TypingIndicator users={typingUsers} />

      {/* Compose */}
      {chatId && (
        <div className="border-t border-base-400 bg-base-100 rounded-b-xl shrink-0">
          {sendError && <div className="text-xs text-error px-3 pt-1">Message failed to send. Try again.</div>}
          {replyTo && (
            <div className="px-3 pt-2">
              <ComposeReplyPreview replyTo={replyTo} onClear={() => setReplyTo(null)} />
            </div>
          )}
          {composePreview && (
            <div className="px-3 pt-2">
              <LinkPreviewCard linkPreview={composePreview} onDismiss={dismissComposePreview} />
            </div>
          )}
          <div className="flex items-end gap-1 px-2 py-1">
            <div className="flex-1 min-w-0 self-center">
              <ChatComposerEditor
                key={claimId}
                ref={editorRef}
                autoFocus={autoFocus}
                onSend={handleSend}
                onChange={setDraftContent}
                onEditPrevious={editPreviousMessage}
                chatType={display.type}
                initialContent={initialDraft}
                uploadUrl={uploadUrl}
                mentionableUsers={mentionableUsers}
                mentionsEnabled={supportsMentions}
                claimId={claimId}
              />
            </div>
            {uploadUrl && (
              <button
                type="button"
                className="btn btn-sm btn-ghost btn-square shrink-0 mb-1"
                onClick={() => editorRef.current?.triggerUpload()}
                aria-label="Attach file"
              >
                <span className="material-symbols-outlined text-lg">attach_file</span>
              </button>
            )}
            {klipyApiKey && (
              <GifPicker klipyApiKey={klipyApiKey} onSelectGif={handleSelectGif} buttonClassName="btn-sm" />
            )}
            <button
              type="button"
              className="btn btn-sm btn-ghost btn-square shrink-0 mb-1"
              disabled={sending}
              onClick={() => editorRef.current?.send()}
              aria-label="Send"
            >
              <span className="material-symbols-outlined text-lg">arrow_upward</span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
