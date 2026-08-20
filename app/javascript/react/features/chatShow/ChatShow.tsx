import { useQuery } from "@tanstack/react-query"
import { getRouteApi, Link } from "@tanstack/react-router"
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react"

import { isNativeShell } from "~/nativeShell"
import { BackButton } from "~/react/composites/BackButton"
import type { ChatEditorHandle } from "~/react/composites/chat/ChatComposerEditor"
import { ChatHeaderAvatar } from "~/react/composites/chat/ChatHeaderAvatar"
import { TypingIndicator } from "~/react/composites/chat/TypingIndicator"
import { MailboxActionBar, mailboxActionUrls } from "~/react/composites/MailboxActionBar"
import type { MailboxState } from "~/react/composites/MailboxActionBar"
import { SubscriptionBell } from "~/react/composites/SubscriptionBell"
import { attachmentUploadUrl } from "~/react/shared/attachmentUrls"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDecisions } from "~/react/shared/hooks/useDecisions"
import { useDisableDocumentScrollAnchor } from "~/react/shared/hooks/useDisableDocumentScrollAnchor"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"
import { useDropzone } from "~/react/shared/hooks/useDropzone"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { type MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import { useRefocusOnEditClose } from "~/react/shared/hooks/useRefocusOnEditClose"
import { useScrollToReply } from "~/react/shared/hooks/useScrollToReply"
import { useViewportFillHeight } from "~/react/shared/hooks/useViewportFillHeight"
import { lastOwnItemId } from "~/react/shared/lastOwnItem"
import { parseMailboxNavigationContext } from "~/react/shared/mailboxNavigation"
import { SOURCE_META } from "~/react/shared/notificationSources"
import { isIOS } from "~/react/shared/platform"
import {
  EMPTY_MAILBOX_VIEW_IDENTIFIER,
  focusEntryIsNavigable,
  mailboxViewIndexQueryOptions,
} from "~/react/shared/queries/mailboxViewIndex"
import type { BackNavigation, ChatMetadata, MailboxEntryResponse } from "~/react/shared/types"
import type { BottomSheetHandle } from "~/react/ui/BottomSheet"
import { DropzoneOverlay } from "~/react/ui/DropzoneOverlay"
import { ErrorState } from "~/react/ui/ErrorState"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { chatBackNavigation } from "./chatBackNavigation"
import { ChatShowSkeleton } from "./ChatShowSkeleton"
import { CollaboratorPanel } from "./CollaboratorPanel"
import { ComposeBar } from "./ComposeBar"
import { GroupCollaboratorPanel } from "./GroupCollaboratorPanel"
import { MessageList } from "./MessageList"
import { useChatCollaborators } from "./useChatCollaborators"
import { useChatShowState } from "./useChatShowState"

// The route id carries the pathless shell parent prefix (shellRoute has id
// "shell"), so the typed accessor is addressed as "/shell/chats/$chatId".
const routeApi = getRouteApi("/shell/chats/$chatId")

type RenameChat = (title: string | null) => Promise<{ error?: string }>

// Android Chrome's default `interactive-widget=resizes-visual` shrinks the
// visual viewport when the soft keyboard opens but leaves the layout viewport
// (and `document.documentElement.scrollHeight`) untouched. ComposeBar already
// re-pins itself above the keyboard via `bottom: keyboardHeight`, but the
// messages just above it sit at their natural document positions — which now
// fall behind the keyboard with no room left to scroll past. Padding the body
// extends the scrollable range so the latest messages can be brought into the
// visual viewport, and we follow the user there if they were already at the
// bottom.
// Skipped on iOS (Safari and the native WKWebView shell, which shares the same
// WebKit engine): the layout viewport shrinks with the keyboard, so ComposeBar
// already sits at the keyboard top with no body padding. The visualViewport
// readings still report nonzero amounts that vary as the page pans, and padding
// the body off those readings makes pin-to-bottom overshoot the composer's flow
// position — the composer beaches above the keyboard.
export function useKeyboardAwareBodyPadding() {
  useEffect(() => {
    if (isIOS()) return
    const vv = window.visualViewport
    if (!vv) return

    let prevKeyboardHeight = 0
    const update = () => {
      const keyboardHeight = Math.max(0, window.innerHeight - (vv.height + vv.offsetTop))
      if (keyboardHeight === prevKeyboardHeight) return
      // Snapshot bottom-stickiness against the pre-change scrollHeight, since
      // mutating padding shifts it.
      const wasNearBottom = document.documentElement.scrollHeight - window.scrollY - window.innerHeight < 50
      document.body.style.paddingBottom = keyboardHeight > 0 ? `${keyboardHeight}px` : ""
      prevKeyboardHeight = keyboardHeight
      if (wasNearBottom) {
        window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" })
      }
    }

    vv.addEventListener("resize", update)
    vv.addEventListener("scroll", update)
    return () => {
      vv.removeEventListener("resize", update)
      vv.removeEventListener("scroll", update)
      document.body.style.paddingBottom = ""
    }
  }, [])
}

// Touch devices: dragging the conversation dismisses the keyboard (Discord /
// iMessage behavior). On the native WKWebView we additionally jump the composer
// to the latest messages on focus, so the keyboard is only ever open while
// pinned at the bottom — the only state where the fixed composer stays put there
// (scrolling with the keyboard up beaches it mid-screen). Programmatic scrolls
// (auto-scroll after send) fire no touchmove/focusin, so they're unaffected.
//
// The focus scroll-to-bottom is native-only: on mobile Safari the sticky
// composer re-sticks itself, and scrolling to scrollHeight overscrolls past the
// content — iOS Safari doesn't shrink the layout viewport for the keyboard, so
// it exposes viewport background below the bar (a gap outside the DOM). The
// touchmove dismiss runs on both, so Safari closes the keyboard on scroll too.
function useKeyboardScrollGuard(isMobile: boolean) {
  useEffect(() => {
    // Gate on the mobile composer being rendered (same signal ComposeBar uses),
    // not pointer type: on iPad (desktop UA) the desktop composer renders, so
    // pointer:coarse would run this against a composer that doesn't exist and
    // blur it on scroll.
    if (!isMobile) return

    const activeEditable = () => {
      const el = document.activeElement as HTMLElement | null
      return el?.isContentEditable ? el : null
    }
    const inComposer = (node: EventTarget | null) =>
      node instanceof Node && !!document.querySelector("[data-chat-composer]")?.contains(node)

    const onTouchMove = (e: TouchEvent) => {
      const editable = activeEditable()
      if (editable && !inComposer(e.target)) editable.blur()
    }
    window.addEventListener("touchmove", onTouchMove, { passive: true })

    const onFocusIn = isNativeShell()
      ? (e: FocusEvent) => {
          if (!inComposer(e.target)) return
          requestAnimationFrame(() =>
            window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" })
          )
        }
      : null
    if (onFocusIn) document.addEventListener("focusin", onFocusIn)

    return () => {
      window.removeEventListener("touchmove", onTouchMove)
      if (onFocusIn) document.removeEventListener("focusin", onFocusIn)
    }
  }, [isMobile])
}

function RenameTitle({
  initialValue,
  onSave,
  onCancel,
}: {
  initialValue: string
  onSave: RenameChat
  onCancel: () => void
}) {
  const [value, setValue] = useState(initialValue)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  // Enter fires onSubmit, which also triggers onBlur as the input loses focus.
  // A state-based guard is stale between those two calls — use a synchronous
  // ref to ensure we only issue one PATCH per edit.
  const inFlightRef = useRef(false)

  useEffect(() => {
    inputRef.current?.select()
  }, [])

  // After a 422, re-focus the input. Runs after React has flushed state so
  // readOnly/saving have settled and focus() actually lands.
  useEffect(() => {
    if (error) inputRef.current?.focus()
  }, [error])

  async function save(next: string | null) {
    if (inFlightRef.current) return
    inFlightRef.current = true
    setSaving(true)
    try {
      const result = await onSave(next)
      if (result.error) {
        setError(result.error)
        return
      }
      onCancel()
    } finally {
      inFlightRef.current = false
      setSaving(false)
    }
  }

  async function submit() {
    const trimmed = value.trim()
    if (trimmed === initialValue.trim()) {
      onCancel()
      return
    }
    await save(trimmed || null)
  }

  return (
    <form
      className="flex-1 min-w-0 flex flex-col gap-1"
      onSubmit={e => {
        e.preventDefault()
        void submit()
      }}
    >
      <div className="flex items-center gap-1">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={e => {
            setValue(e.target.value)
            if (error) setError(null)
          }}
          onKeyDown={e => {
            if (e.key === "Escape") {
              e.preventDefault()
              onCancel()
            }
          }}
          onBlur={() => void submit()}
          aria-label="Chat name"
          aria-invalid={error ? "true" : undefined}
          // readOnly (not disabled) so Escape still fires onKeyDown while
          // a save is in flight — otherwise the user is stuck on a slow PATCH.
          readOnly={saving}
          className={`input input-sm flex-1 min-w-0 ${error ? "input-error" : ""} ${saving ? "opacity-60" : ""}`}
          maxLength={200}
        />
        <button
          type="button"
          // preventDefault on mousedown keeps focus on the input, so onBlur
          // doesn't fire before our onClick handler runs.
          onMouseDown={e => e.preventDefault()}
          onClick={() => void save(null)}
          disabled={saving}
          className="btn btn-ghost btn-sm shrink-0"
          title="Reset to default name"
        >
          Clear
        </button>
      </div>
      {error && (
        <div role="alert" className="text-xs font-medium bg-error text-error-content rounded-md px-2 py-1">
          {error}
        </div>
      )}
    </form>
  )
}

function ChatHeaderRow({
  metadata,
  back,
  collaboratorCount,
  currentUserId,
  onRename,
  onToggleCollaborators,
  inline = false,
}: {
  metadata: ChatMetadata
  back: BackNavigation | null
  collaboratorCount: number
  currentUserId: string
  onRename: RenameChat
  onToggleCollaborators?: () => void
  // Rendered inside the mailbox action row (as a trailing slot) rather than as a
  // standalone header row: drop the row padding and bound the title instead of
  // letting it flex-grow (which would collapse to zero inside the shrink-wrapped slot).
  inline?: boolean
}) {
  const showCollaboratorCount = metadata.type === "group" || metadata.type === "multi"
  const canRename = metadata.type === "multi"
  const [isEditing, setIsEditing] = useState(false)

  return (
    <div className={`flex items-center gap-2 ${inline ? "min-w-0" : "p-2"}`}>
      {back && <BackButton back={back} iconOnly navLink />}
      <div className="shrink-0">
        <ChatHeaderAvatar
          type={metadata.type}
          collaborators={metadata.collaborators}
          currentUserId={currentUserId}
          size="medium"
        />
      </div>
      {isEditing && canRename ? (
        <RenameTitle initialValue={metadata.chat_title} onSave={onRename} onCancel={() => setIsEditing(false)} />
      ) : (
        <h1
          className={`text-base font-accent truncate flex items-center gap-1.5 group/title ${
            inline ? "min-w-0 max-w-[14rem] mr-2" : "flex-1 min-w-0"
          }`}
        >
          <span className="truncate min-w-0">{metadata.chat_title}</span>
          {canRename && (
            <button
              type="button"
              onClick={() => setIsEditing(true)}
              aria-label="Rename chat"
              title="Rename chat"
              className="shrink-0 text-base-content/30 hover:text-base-content/60 opacity-0 group-hover/title:opacity-100 focus-visible:opacity-100 transition-opacity"
            >
              <span className="material-symbols-outlined leading-none" style={{ fontSize: "16px" }}>
                edit
              </span>
            </button>
          )}
        </h1>
      )}
      {!isEditing && (
        <button
          type="button"
          onClick={() => {
            window.dispatchEvent(
              new CustomEvent("open-chat-panel", {
                detail: { kind: "chat", chatId: metadata.chat_id, title: metadata.chat_title },
              })
            )
          }}
          aria-label="Open in panel"
          title="Open in panel"
          className="@mobile:hidden @desktop:inline-flex shrink-0 btn btn-square"
        >
          <span className="material-symbols-outlined leading-none text-lg rotate-90">open_in_new</span>
        </button>
      )}
      {onToggleCollaborators && !isEditing && metadata.type !== "self" && (
        <button
          type="button"
          onClick={onToggleCollaborators}
          aria-label="Show members"
          title="Members"
          className="@mobile:hidden @desktop:inline-flex shrink-0 btn"
        >
          <span className="material-symbols-outlined leading-none text-lg">person</span>
          {showCollaboratorCount && <span className="leading-none">{collaboratorCount}</span>}
        </button>
      )}
      {!isEditing && metadata.type !== "self" && (
        <SubscriptionBell
          workspaceId={metadata.workspace_id}
          options={{
            all: { hint: SOURCE_META.Chat.allDescription },
            relevant: { hint: SOURCE_META.Chat.relevantDescription },
            default: { hint: "Use your chat settings" },
          }}
          manageUrl="/notifications"
        />
      )}
    </div>
  )
}

function mailboxToState(mailbox: MailboxEntryResponse): MailboxState {
  return {
    isUnread: mailbox.is_unread,
    isArchived: mailbox.is_archived,
    isSnoozed: mailbox.is_snoozed,
    snoozedUntil: mailbox.snoozed_until,
  }
}

const ChatHeader = memo(function ChatHeader({
  metadata,
  back,
  collaboratorCount,
  currentUserId,
  onRename,
  onToggleCollaborators,
  mailboxBack,
}: {
  metadata: ChatMetadata
  back: BackNavigation | null
  collaboratorCount: number
  currentUserId: string
  onRename: RenameChat
  onToggleCollaborators?: () => void
  mailboxBack: BackNavigation | null
}) {
  const mailbox = metadata.mailbox
  // Memoize against `mailbox` (stable across parent re-renders) so the bar's
  // internal optimistic state isn't re-seeded on every render.
  const initialMailboxState = useMemo<MailboxState | null>(() => (mailbox ? mailboxToState(mailbox) : null), [mailbox])
  const actionUrls = useMemo(() => (mailbox ? mailboxActionUrls(mailbox.id) : null), [mailbox])

  // Inbox notification view: fold the mailbox triage actions and the chat
  // identity into a single row — back + archive/read/snooze on the left, the
  // chat avatar/title/actions trailing on the right (mirroring the email header).
  if (mailbox && initialMailboxState && actionUrls && mailboxBack) {
    return (
      <StickyHeader>
        <div className="p-2">
          <MailboxActionBar
            state={initialMailboxState}
            actionUrls={actionUrls}
            mailboxEntryId={mailbox.id}
            back={mailboxBack}
            showSnooze={false}
            trailingSlot={
              <ChatHeaderRow
                inline
                metadata={metadata}
                back={null}
                collaboratorCount={collaboratorCount}
                currentUserId={currentUserId}
                onRename={onRename}
                onToggleCollaborators={onToggleCollaborators}
              />
            }
          />
        </div>
      </StickyHeader>
    )
  }

  return (
    <StickyHeader>
      <ChatHeaderRow
        metadata={metadata}
        back={back}
        collaboratorCount={collaboratorCount}
        currentUserId={currentUserId}
        onRename={onRename}
        onToggleCollaborators={onToggleCollaborators}
      />
    </StickyHeader>
  )
})

export function ChatShow() {
  const { chatId } = routeApi.useParams()
  const { return_to: returnTo, mailbox_entry_id: openedMailboxEntryId } = routeApi.useSearch()
  const back = useMemo(() => chatBackNavigation(returnTo), [returnTo])

  const {
    metadata,
    metadataError,
    messages,
    loading,
    loadingMore,
    hasMore,
    sending,
    sendError,
    editingMessageId,
    typingUsers,
    composePreview,
    loadMore,
    loadNewer,
    loadingNewer,
    hasNewer,
    jumpToMessage,
    jumpToLatest,
    atTail,
    sendMessage,
    editMessage,
    deleteMessage,
    renameChat,
    toggleReaction,
    setEditingMessageId,
    cancelEdit,
    setDraftContent,
    dismissComposePreview,
    claimId,
    replyTo,
    setReplyTo,
    lastReadAt,
    unreadMessageCount,
  } = useChatShowState(chatId)

  // Chat title / group name / "Note to self" — all resolved server-side into
  // chat_title (see Chat.resolved_title), so it isn't known until metadata lands.
  useDocumentTitle(metadata?.chat_title ?? "Chat")

  const { user: currentUser, clientConfig, error: userError } = useCurrentUser()
  const klipyApiKey = clientConfig?.klipy_api_key ?? null

  // Opened from a navigable mailbox list ⇒ the prev/next nav arrows are live, so
  // suppress the composer's initial autofocus: focus in the composer swallows
  // ArrowLeft/ArrowRight and the mailbox hotkeys would never fire. Decide with the same
  // rule the nav hook renders (focusEntryIsNavigable), not an ad-hoc check: the main inbox
  // is always navigable, but a focus view/sort is navigable only once its order is final
  // AND this entry sits in it — otherwise the arrows stay hidden and there's nothing to
  // protect. The editor captures autoFocus once at mount (a later flip can't un-focus it),
  // so while the index is still loading on a cold direct load — when we don't yet know —
  // assume navigable and suppress: a composer that steals the arrow hotkeys is the worse
  // failure than a briefly-unfocused composer on a view that turns out non-navigable.
  // Derived from the typed return_to (not a one-time window.location read) so it
  // re-evaluates when a chat→chat client navigation changes the URL without remounting;
  // keyed off the URL's mailbox_entry_id, which — unlike the async metadata — is present
  // at mount, when the autofocus decision is made.
  const navContext = useMemo(
    () => parseMailboxNavigationContext(returnTo ? `?return_to=${encodeURIComponent(returnTo)}` : ""),
    [returnTo]
  )
  const focusIdentifier = navContext?.kind === "focus" ? navContext.identifier : null
  const focusIndex = useQuery({
    ...mailboxViewIndexQueryOptions(focusIdentifier ?? EMPTY_MAILBOX_VIEW_IDENTIFIER),
    enabled: focusIdentifier !== null,
  })
  const openedFromMailbox =
    navContext !== null &&
    (navContext.kind === "inbox" ||
      focusIndex.isPending ||
      focusEntryIsNavigable(focusIndex.data, openedMailboxEntryId ?? ""))

  // Decisions are workspace-scoped and refetched on the DECISIONS_CHANGED signal
  // riding the workspace_events topic (metadata loads async, so workspaceId is
  // empty until the chat-show fetch resolves — useDecisions gates on it).
  const { decisionsByGid, toggleDecision } = useDecisions({
    workspaceId: metadata?.workspace_id ?? "",
  })

  const { scrollToReply, scrollingToReplyRef, scrollingToId } = useScrollToReply(jumpToMessage)

  const { collaborators, archived, selfRemoved, selfLeave, addCollaborator, removeCollaborator } =
    useChatCollaborators(chatId, metadata?.workspace_id ?? null, currentUser?.id ?? null)
  const [panelOpen, setPanelOpen] = useState(false)
  const collaboratorPanelRef = useRef<BottomSheetHandle>(null)

  useKeyboardAwareBodyPadding()
  useKeyboardScrollGuard(useIsMobile())
  useDisableDocumentScrollAnchor()

  const wrapperRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<ChatEditorHandle>(null)
  const handleDroppedFiles = useCallback((files: File[]) => {
    editorRef.current?.uploadFiles(files)
  }, [])

  useRefocusOnEditClose(
    editingMessageId,
    useCallback(() => editorRef.current?.focus(), [])
  )

  const currentUserId = currentUser?.id ?? null

  // Mention candidates are the chat's collaborators, including yourself — mentioning
  // yourself works like mentioning anyone else. Built straight from the collaborator
  // list we already hold rather than intersecting the org-members store, so a
  // collaborator who isn't an org member (e.g. a guest, or one added before the store
  // refetches) stays mentionable. The live collaborator set takes precedence over the snapshot.
  const mentionableUsers = useMemo<MentionUser[]>(() => {
    const source = collaborators.length ? collaborators : (metadata?.collaborators ?? [])
    return source.map(c => ({ id: c.user.id, display_name: c.user.display_name, is_collaborator: true }))
  }, [collaborators, metadata?.collaborators])

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
  const { isDragOver, ref: dropzoneRef } = useDropzone({ onFiles: handleDroppedFiles })
  const setWrapperRef = useCallback(
    (el: HTMLDivElement | null) => {
      wrapperRef.current = el
      dropzoneRef(el)
    },
    [dropzoneRef]
  )

  // Fill the viewport so the sticky ComposeBar sits at its bottom even when the
  // conversation is too short to scroll.
  useViewportFillHeight(wrapperRef, !loading && !!metadata)

  if (userError) {
    return <ErrorState message="Failed to load user data. Please try refreshing the page." />
  }
  if (metadataError) {
    return <ErrorState message="Could not load this chat." />
  }
  if (loading || !metadata || !currentUser) {
    return <ChatShowSkeleton />
  }

  const canCompose = !archived && !selfRemoved
  // Drives the mailbox action bar's "back" affordance. The bar shows only when the
  // chat was opened *from* the inbox — i.e. the URL carries the mailbox_entry_id
  // (parity with the pre-SPA server gate, get_mailbox_entry_for_resource). A chat
  // that merely has an inbox entry, opened from the chat list, keeps the plain header.
  // Read from the typed search (not window.location) so it stays correct after a
  // client navigation to a neighbor entry, where the document isn't reloaded.
  const hasMailboxEntry = metadata.mailbox != null && openedMailboxEntryId === metadata.mailbox.id
  const collaboratorCount = collaborators.length || metadata.collaborators.length
  // Close through the panel's imperative handle so it plays its exit animation;
  // its onClose then flips panelOpen to unmount. Opening mounts it directly.
  const toggleCollaborators = () => {
    if (panelOpen) {
      collaboratorPanelRef.current?.close()
    } else {
      setPanelOpen(true)
    }
  }

  // -mb-12 counteracts the layout wrapper's pb-12 so the sticky
  // ComposeBar doesn't detach from the viewport at the bottom
  return (
    <div ref={setWrapperRef} id="chat-show" className="-mb-12 flex flex-col relative">
      {isDragOver && canCompose && <DropzoneOverlay centerOnScreen />}
      <ChatHeader
        metadata={metadata}
        back={back}
        collaboratorCount={collaboratorCount}
        currentUserId={currentUser.id}
        onRename={renameChat}
        onToggleCollaborators={toggleCollaborators}
        mailboxBack={hasMailboxEntry ? back : null}
      />
      {/* Message content stays narrow; the ComposeBar below spans the wider shell. */}
      <div className="w-full max-w-3xl mx-auto flex flex-col flex-1">
        {archived && <ArchivedBanner conflictingDmId={archived.conflictingDmId} />}
        {selfRemoved && !archived && (
          <div className="rounded-lg border border-base-300 bg-base-200 px-3 py-2 text-sm mb-4" role="status">
            You were removed from this conversation.
          </div>
        )}
        <div className="flex-1 pb-4">
          <MessageList
            messages={messages}
            loadingMore={loadingMore}
            hasMore={hasMore}
            currentUserId={currentUser.id}
            chatTitle={metadata.chat_title}
            chatType={metadata.type}
            isGroupChat={metadata.is_group_chat}
            collaborators={collaborators.length ? collaborators : metadata.collaborators}
            memberCount={collaboratorCount}
            onAddPeople={() => setPanelOpen(true)}
            onStartMessage={() => editorRef.current?.focus()}
            editingMessageId={editingMessageId}
            lastReadAt={lastReadAt}
            unreadMessageCount={unreadMessageCount}
            uploadUrl={attachmentUploadUrl(metadata.workspace_id)}
            mentionableUsers={mentionableUsers}
            mentionsEnabled={metadata.supports_mentions}
            klipyApiKey={klipyApiKey}
            onLoadMore={loadMore}
            onLoadNewer={loadNewer}
            loadingNewer={loadingNewer}
            hasNewer={hasNewer}
            onScrollTo={scrollToReply}
            scrollingToReplyRef={scrollingToReplyRef}
            scrollingToId={scrollingToId}
            atTail={atTail}
            onJumpToLatest={jumpToLatest}
            onEdit={setEditingMessageId}
            onCancelEdit={cancelEdit}
            onSaveEdit={editMessage}
            onDelete={deleteMessage}
            onReact={toggleReaction}
            onReply={setReplyTo}
            decisionsByGid={decisionsByGid}
            onToggleDecision={toggleDecision}
          />
          <TypingIndicator users={typingUsers} />
        </div>
      </div>
      {canCompose && (
        <ComposeBar
          currentUser={{
            id: currentUser.id,
            displayName: currentUser.display_name,
            picture: currentUser.picture,
          }}
          sending={sending}
          sendError={sendError}
          composePreview={composePreview}
          uploadUrl={attachmentUploadUrl(metadata.workspace_id)}
          mentionableUsers={mentionableUsers}
          mentionsEnabled={metadata.supports_mentions}
          klipyApiKey={klipyApiKey}
          chatType={metadata.type}
          claimId={claimId}
          replyTo={replyTo}
          editorRef={editorRef}
          onSend={sendMessage}
          onChange={setDraftContent}
          onEditPrevious={editPreviousMessage}
          onDismissPreview={dismissComposePreview}
          onClearReply={() => setReplyTo(null)}
          suppressInitialAutoFocus={openedFromMailbox}
        />
      )}
      {panelOpen && metadata.type !== "group" && (
        <CollaboratorPanel
          ref={collaboratorPanelRef}
          collaborators={collaborators}
          currentUserId={currentUser.id}
          canLeave={metadata.type !== "dm"}
          onClose={() => setPanelOpen(false)}
          onAdd={addCollaborator}
          onLeave={() => removeCollaborator(currentUser.id)}
        />
      )}
      {panelOpen && metadata.type === "group" && metadata.group_id && (
        <GroupCollaboratorPanel
          ref={collaboratorPanelRef}
          groupId={metadata.group_id}
          collaborators={collaborators}
          currentUserId={currentUser.id}
          onClose={() => setPanelOpen(false)}
          onSelfLeave={selfLeave}
        />
      )}
    </div>
  )
}

function ArchivedBanner({ conflictingDmId }: { conflictingDmId: string | null }) {
  if (conflictingDmId) {
    return (
      <div className="rounded-lg border border-warning bg-warning/10 px-3 py-2 text-sm mb-4" role="status">
        This conversation has been merged.{" "}
        <Link to="/chats/$chatId" params={{ chatId: conflictingDmId }} className="link link-primary">
          Continue in your DM
        </Link>
        .
      </div>
    )
  }
  return (
    <div className="rounded-lg border border-warning bg-warning/10 px-3 py-2 text-sm mb-4" role="status">
      This conversation has been archived.
    </div>
  )
}
