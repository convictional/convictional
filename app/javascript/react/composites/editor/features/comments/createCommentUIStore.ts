import { createStore } from "zustand/vanilla"

import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"

// UI / ephemeral client state for the comment system. Server state (the threads
// themselves, their mutations and channel patches) lives in the TanStack Query
// cache via useCommentThreads — this store holds only what's local to the tab:
// the active selection, the in-progress comment card, and editing/reply drafts.
export interface CommentUIState {
  activeCommentId: string | null
  activating: boolean
  showCommentCard: boolean
  commentCardTop: number
  pendingCommentId: string
  selectedQuotedText: string
  replyToId: string | null
  editingCommentId: string | null
  showReactionPicker: boolean
}

export interface CommentUIStore extends CommentUIState {
  // The viewer's identity, used for ownership checks (CommentMenu) and the
  // optimistic reaction toggle. Not server state — it's the current user.
  currentUserId: string
  currentUserName: string
  // Mention candidates from the org-members store, kept in sync by CommentSystem.
  mentionableUsers: MentionUser[]

  init: (currentUserId: string, currentUserName: string) => void

  setActiveComment: (id: string | null) => void
  openCommentCard: (top: number, quotedText: string, pendingId: string) => void
  closeCommentCard: () => void
  setReplyTo: (markId: string | null) => void
  setEditingComment: (commentId: string | null) => void
  openReactionPicker: (quotedText: string, pendingId: string) => void
  closeReactionPicker: () => void
  setCommentCardTop: (top: number) => void
}

const initialUIState: CommentUIState = {
  activeCommentId: null,
  activating: false,
  showCommentCard: false,
  commentCardTop: 0,
  pendingCommentId: "",
  selectedQuotedText: "",
  replyToId: null,
  editingCommentId: null,
  showReactionPicker: false,
}

export function createCommentUIStore() {
  return createStore<CommentUIStore>(set => ({
    ...initialUIState,
    currentUserId: "",
    currentUserName: "",
    mentionableUsers: [],

    init: (currentUserId, currentUserName) => {
      // Reset UI state — this module-level store is reused across navigations,
      // so clear stale UI (an open card, a stale selection) from a previous resource.
      set({ currentUserId, currentUserName, ...initialUIState })
    },

    setActiveComment: id => set({ activeCommentId: id }),

    openCommentCard: (top, quotedText, pendingId) =>
      set({
        showCommentCard: true,
        commentCardTop: top,
        selectedQuotedText: quotedText,
        pendingCommentId: pendingId,
      }),

    closeCommentCard: () =>
      set({
        showCommentCard: false,
        pendingCommentId: "",
        selectedQuotedText: "",
        activeCommentId: null,
      }),

    setReplyTo: markId => set({ replyToId: markId }),
    setEditingComment: commentId => set({ editingCommentId: commentId }),
    openReactionPicker: (quotedText, pendingId) =>
      set({ showReactionPicker: true, selectedQuotedText: quotedText, pendingCommentId: pendingId }),
    closeReactionPicker: () =>
      set({
        showReactionPicker: false,
        pendingCommentId: "",
        activeCommentId: null,
      }),
    setCommentCardTop: top => set({ commentCardTop: top }),
  }))
}
