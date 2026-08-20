import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useRef, useState } from "react"

import { chatMetadataQueryOptions } from "~/react/composites/chat/chatMetadata"
import { useChat } from "~/react/composites/chat/useChat"
import { apiFetch } from "~/react/shared/apiFetch"
import { attachmentUploadUrl } from "~/react/shared/attachmentUrls"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import type { ChatCreatedResponse } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"
import type { ChatPanelDisplay, ChatPanelState, OpenChatPanelEvent } from "./types"

const STORAGE_KEY = "chat-panel-state"
const LEGACY_STORAGE_KEY = "dm-panel-state"
const DRAFT_DEBOUNCE_MS = 500

// Pre-`display` shape: state stored a `recipient` field instead. Migrating
// readers (here only) is enough — writers always use the new shape.
interface LegacyChatPanelState {
  chatId: string | null
  workspaceId: string | null
  uploadUrl: string | null
  supportsMentions?: boolean
  recipient?: { id: string; displayName: string; picture: string | null }
  display?: ChatPanelDisplay
  minimized: boolean
  draftContent: string
  incomplete?: boolean
  loadFailed?: boolean
}

function migrateLoaded(parsed: LegacyChatPanelState): ChatPanelState {
  if (parsed.display) {
    return {
      chatId: parsed.chatId,
      workspaceId: parsed.workspaceId ?? null,
      uploadUrl: parsed.uploadUrl,
      supportsMentions: parsed.supportsMentions ?? false,
      display: parsed.display,
      minimized: parsed.minimized,
      draftContent: parsed.draftContent,
      // Entries persisted before workspaceId tracking lack it; force a metadata
      // reconcile so the chat subscription can name its topic.
      incomplete: (parsed.incomplete ?? false) || (!!parsed.chatId && !parsed.workspaceId),
      loadFailed: false,
    }
  }
  const recipient = parsed.recipient
  const display: ChatPanelDisplay = recipient
    ? {
        title: recipient.displayName,
        type: "dm",
        collaborators: [
          {
            id: recipient.id,
            user: { id: recipient.id, display_name: recipient.displayName, picture: recipient.picture },
          },
        ],
      }
    : { title: "Chat", type: "dm", collaborators: [] }
  return {
    chatId: parsed.chatId,
    workspaceId: parsed.workspaceId ?? null,
    uploadUrl: parsed.uploadUrl,
    supportsMentions: parsed.supportsMentions ?? false,
    display,
    minimized: parsed.minimized,
    draftContent: parsed.draftContent,
    incomplete: !parsed.chatId || !parsed.workspaceId,
    loadFailed: false,
  }
}

function loadState(): ChatPanelState | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) return migrateLoaded(JSON.parse(raw) as LegacyChatPanelState)
    const legacy = sessionStorage.getItem(LEGACY_STORAGE_KEY)
    if (!legacy) return null
    sessionStorage.setItem(STORAGE_KEY, legacy)
    sessionStorage.removeItem(LEGACY_STORAGE_KEY)
    return migrateLoaded(JSON.parse(legacy) as LegacyChatPanelState)
  } catch {
    return null
  }
}

function saveState(state: ChatPanelState | null): void {
  if (state) {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } else {
    sessionStorage.removeItem(STORAGE_KEY)
  }
}

function recipientDisplay(target: { id: string; displayName: string; picture: string | null }): ChatPanelDisplay {
  return {
    title: target.displayName,
    type: "dm",
    collaborators: [
      { id: target.id, user: { id: target.id, display_name: target.displayName, picture: target.picture } },
    ],
  }
}

export function useChatPanelState() {
  const [initialState] = useState<ChatPanelState | null>(loadState)
  const [panelState, setPanelState] = useState<ChatPanelState | null>(initialState)
  const [creatingChat, setCreatingChat] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const requestIdRef = useRef(0)
  const draftTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Tracks whether openChatPanel/openChatPanelForUser just set the chatId, so the auto-close
  // effect can distinguish "panel was opened here" from "user navigated to this chat."
  const openedByPanelRef = useRef(false)
  // Always-current panelState for use in effect cleanups, which would
  // otherwise capture a stale closure value.
  const panelStateRef = useRef(panelState)
  panelStateRef.current = panelState

  const queryClient = useQueryClient()
  const { user } = useCurrentUser()
  const currentUserId = user?.id ?? null
  const currentUserDisplayName = user?.display_name ?? null

  const chat = useChat({
    chatId: panelState?.chatId ?? null,
    workspaceId: panelState?.workspaceId ?? null,
    currentUserId,
    currentUserDisplayName,
    initialDraft: initialState?.draftContent ?? "",
    markReadOnOpen: true,
    enableTyping: true,
  })

  const { draftContent } = chat

  // Persist state changes to sessionStorage immediately
  useEffect(() => {
    saveState(panelState)
  }, [panelState])

  // Debounce draft persistence to avoid sessionStorage writes on every keystroke
  useEffect(() => {
    if (!panelState) return
    draftTimerRef.current = setTimeout(() => {
      if (panelStateRef.current) saveState({ ...panelStateRef.current, draftContent })
    }, DRAFT_DEBOUNCE_MS)
    return () => {
      if (draftTimerRef.current) clearTimeout(draftTimerRef.current)
      if (panelStateRef.current) saveState({ ...panelStateRef.current, draftContent })
    }
  }, [draftContent]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-close when navigating to the same chat's full page.
  // Skip if the chatId was just set by openChatPanel/openChatPanelForUser (the user opened the panel
  // while already on the chat page — closing it immediately would be jarring).
  useEffect(() => {
    if (openedByPanelRef.current) {
      openedByPanelRef.current = false
      return
    }
    if (panelState?.chatId && window.location.pathname === `/chats/${panelState.chatId}`) {
      setPanelState(null)
    }
  }, [panelState?.chatId])

  // Reconcile placeholder/synthesized state with server truth whenever a panel
  // marks itself incomplete: opens by chat-id (placeholder display), opens by
  // recipient (synthesized collaborator after POST resolves), and legacy
  // sessionStorage entries that predate metadata tracking. Messages are
  // re-fetched by useChat's useCatchUpMessages.
  const chatId = panelState?.chatId ?? null
  const incomplete = panelState?.incomplete ?? false
  const loadFailed = panelState?.loadFailed ?? false
  useEffect(() => {
    if (!chatId || !incomplete || loadFailed) return
    // Share the page's metadata cache: ensureQueryData returns the cached
    // ChatMetadata if the show page already fetched it, otherwise fetches once.
    // The `cancelled` guard drops a stale write when the panel switches chats
    // mid-flight (the show page's own subscriptions keep the cache fresh after).
    let cancelled = false
    queryClient
      .ensureQueryData(chatMetadataQueryOptions(chatId))
      .then(detail => {
        if (cancelled) return
        setPanelState(prev =>
          prev?.chatId === chatId
            ? {
                ...prev,
                workspaceId: detail.workspace_id,
                uploadUrl: attachmentUploadUrl(detail.workspace_id),
                supportsMentions: detail.supports_mentions,
                display: {
                  title: detail.chat_title,
                  type: detail.type,
                  collaborators: detail.collaborators,
                },
                incomplete: false,
                loadFailed: false,
              }
            : prev
        )
      })
      .catch(() => {
        if (cancelled) return
        // Keep panel and draft intact; surface a retry affordance instead of
        // discarding work on a transient network blip.
        setPanelState(prev => (prev?.chatId === chatId ? { ...prev, loadFailed: true } : prev))
      })
    return () => {
      cancelled = true
    }
  }, [chatId, incomplete, loadFailed, queryClient])

  const openChatPanel = useCallback((chatId: string, hint?: { title?: string; picture?: string | null }) => {
    // Same chat already open — just restore.
    if (panelStateRef.current?.chatId === chatId) {
      setPanelState(prev => (prev ? { ...prev, minimized: false } : null))
      return
    }
    abortRef.current?.abort()
    openedByPanelRef.current = true
    setPanelState({
      chatId,
      workspaceId: null,
      uploadUrl: null,
      supportsMentions: false,
      display: { title: hint?.title ?? "Chat", type: "dm", collaborators: [] },
      minimized: false,
      draftContent: "",
      incomplete: true,
      loadFailed: false,
    })
  }, [])

  const openChatPanelForUser = useCallback(
    async (recipient: { id: string; displayName: string; picture: string | null }) => {
      // Create-or-fetch the DM via the chats API.
      const sameRecipientOpen =
        panelStateRef.current?.display.type === "dm" &&
        panelStateRef.current.display.collaborators.some(c => c.user.id === recipient.id)
      if (sameRecipientOpen) {
        setPanelState(prev => (prev ? { ...prev, minimized: false } : null))
        return
      }

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      const thisRequest = ++requestIdRef.current

      setPanelState({
        chatId: null,
        workspaceId: null,
        uploadUrl: null,
        supportsMentions: false,
        display: recipientDisplay(recipient),
        minimized: false,
        draftContent: "",
        incomplete: false,
        loadFailed: false,
      })
      setCreatingChat(true)

      try {
        const data = await apiFetch<ChatCreatedResponse>("/api/chats", {
          method: "POST",
          body: JSON.stringify({ recipient_ids: [recipient.id] }),
          signal: controller.signal,
        })
        if (requestIdRef.current !== thisRequest) return
        openedByPanelRef.current = true
        setPanelState(prev => {
          // Confirm this update still belongs to the same open call by
          // checking the synthesized collaborator id is still present.
          const stillOurs = prev && prev.display.collaborators.some(c => c.user.id === recipient.id)
          if (!stillOurs) return prev
          return {
            ...prev,
            chatId: data.chat_id,
            workspaceId: data.workspace_id,
            uploadUrl: attachmentUploadUrl(data.workspace_id),
            supportsMentions: data.supports_mentions,
            // Reconcile synthesized collaborator with server truth (group
            // membership, type, etc.) via the metadata-fetch effect.
            incomplete: true,
          }
        })
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return
        if (requestIdRef.current !== thisRequest) return
        showFlash("Couldn't open conversation.")
        setPanelState(null)
      } finally {
        if (requestIdRef.current === thisRequest) {
          setCreatingChat(false)
        }
      }
    },
    []
  )

  const minimize = useCallback(() => {
    setPanelState(prev => (prev ? { ...prev, minimized: true } : null))
  }, [])

  const restore = useCallback(() => {
    setPanelState(prev => (prev ? { ...prev, minimized: false } : null))
  }, [])

  const close = useCallback(() => {
    setPanelState(null)
  }, [])

  const retryLoad = useCallback(() => {
    setPanelState(prev => (prev?.loadFailed ? { ...prev, loadFailed: false } : prev))
  }, [])

  useEffect(() => {
    function handleOpen(e: Event) {
      const detail = (e as CustomEvent<OpenChatPanelEvent>).detail
      switch (detail.kind) {
        case "chat":
          openChatPanel(detail.chatId, { title: detail.title, picture: detail.picture })
          return
        case "recipient":
          openChatPanelForUser({
            id: detail.recipientId,
            displayName: detail.recipientName,
            picture: detail.recipientPicture,
          })
          return
      }
    }
    window.addEventListener("open-chat-panel", handleOpen)
    return () => window.removeEventListener("open-chat-panel", handleOpen)
  }, [openChatPanel, openChatPanelForUser])

  return {
    ...chat,
    panelState,
    loading: creatingChat || chat.loading,
    uploadUrl: panelState?.uploadUrl ?? null,
    supportsMentions: panelState?.supportsMentions ?? false,
    currentUserId,
    initialDraft: initialState?.draftContent ?? "",
    openChatPanel,
    openChatPanelForUser,
    minimize,
    restore,
    close,
    retryLoad,
  }
}
