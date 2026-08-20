import { useCallback, useEffect, useRef } from "react"

import { apiFetch } from "~/react/shared/apiFetch"

export interface UseMailboxEntryReadTrackingArgs {
  mailboxEntryId: string | null
  currentUserId: string | null
  enabled: boolean
  // Mark read once on mount and on each resetKey change. Leave off when another
  // mechanism already marks the resource read on open.
  markReadOnMount?: boolean
  // "when-pending" flushes on unmount only if a read was deferred while hidden,
  // so a quiet open→close never POSTs; "always" flushes unconditionally.
  flushOnUnmount?: "always" | "when-pending"
  // Re-arms the mount/unmount effects when it changes (e.g. the chat panel
  // switching chats without unmounting).
  resetKey?: string | null
}

// Keeps a mailbox entry's read state in sync while its resource is open and
// live comments/messages arrive. The server re-applies UNREAD on every incoming
// item, so without a client-side mark_read the inbox would still show the entry
// as unread once the viewer navigates away. Mark read on an incoming non-self
// item while the tab is visible, deferring to a visibility/unmount flush when hidden.
export function useMailboxEntryReadTracking({
  mailboxEntryId,
  currentUserId,
  enabled,
  markReadOnMount = false,
  flushOnUnmount = "always",
  resetKey = null,
}: UseMailboxEntryReadTrackingArgs) {
  // Read inside markRead so the same memoized callback works before and after
  // the caller's show fetch resolves, and skips the POST when there's no mailbox
  // entry (the endpoint requires one).
  const mailboxEntryIdRef = useRef<string | null>(mailboxEntryId)
  mailboxEntryIdRef.current = mailboxEntryId
  const pendingReadRef = useRef(false)

  const markRead = useCallback(() => {
    const entryId = mailboxEntryIdRef.current
    if (!entryId) return
    apiFetch(`/api/mailbox_entries/${entryId}/mark_read`, { method: "POST" }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!enabled || !markReadOnMount || !currentUserId) return
    markRead()
  }, [enabled, markReadOnMount, currentUserId, resetKey, markRead])

  useEffect(() => {
    if (!enabled) return
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible" && pendingReadRef.current) {
        pendingReadRef.current = false
        markRead()
      }
    }
    document.addEventListener("visibilitychange", onVisibilityChange)
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange)
      if (flushOnUnmount === "always" || pendingReadRef.current) markRead()
    }
  }, [enabled, flushOnUnmount, resetKey, markRead])

  const notifyIncoming = useCallback(
    (authorId: string) => {
      if (!enabled || !currentUserId || authorId === currentUserId) return
      if (document.visibilityState === "visible") {
        markRead()
      } else {
        pendingReadRef.current = true
      }
    },
    [enabled, currentUserId, markRead]
  )

  return { notifyIncoming }
}
