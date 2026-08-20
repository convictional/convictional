import { useEditorEventCallback } from "@handlewithcare/react-prosemirror"
import { useCallback, useEffect, useLayoutEffect, useRef } from "react"

import { getRange } from "~/react/composites/editor/features/comments/commentSelection"
import { useCommentStore, useCommentStoreApi } from "~/react/composites/editor/features/comments/CommentStoreContext"
import { useCommentThreadsContext } from "~/react/composites/editor/features/comments/CommentThreadsContext"
import {
  addPendingCommentDecoration,
  clearPendingCommentDecoration,
  commitPendingComment,
} from "~/react/composites/editor/features/comments/pendingCommentDecoration"
import { useCommentMarks } from "~/react/composites/editor/features/comments/useCommentMarks"
import { useCommentPositioning } from "~/react/composites/editor/features/comments/useCommentPositioning"
import type { CommentSystemProps } from "~/react/composites/editor/features/comments/useComments"
import { REACTIONS } from "~/react/shared/reactions"
import { CommentCards } from "./CommentCards"
import { CommentGutter } from "./CommentGutter"

export function CommentSystem({ containerRef, currentUser, mentionableUsers }: CommentSystemProps) {
  const storeApi = useCommentStoreApi()
  const { threads, createComment } = useCommentThreadsContext()

  const showReactionPicker = useCommentStore(s => s.showReactionPicker)
  const activeCommentId = useCommentStore(s => s.activeCommentId)

  useCommentMarks()
  const { editorFocused, cursorInfo, savedSelectionRef, positionGutter, schedulePositionUpdate } =
    useCommentPositioning(containerRef)

  // Ref for clearPendingComment so dismissActiveUI can call it without a forward reference
  const clearPendingCommentRef = useRef<(pendingId: string) => void>(() => {})

  // Dismiss the active comment UI (reaction picker, comment card, or active highlight).
  // Shared by the editor click handler and click-outside handler.
  const dismissActiveUI = useCallback(() => {
    const state = storeApi.getState()
    if (state.showReactionPicker) {
      if (state.pendingCommentId) clearPendingCommentRef.current(state.pendingCommentId)
      state.closeReactionPicker()
    } else if (state.showCommentCard) {
      if (state.pendingCommentId) clearPendingCommentRef.current(state.pendingCommentId)
      state.closeCommentCard()
    } else if (!state.replyToId && !state.editingCommentId && !state.activating) {
      state.setActiveComment(null)
    }
  }, [storeApi])

  // Prevents the cursor gutter buttons from flashing visible between mousedown
  // on a comment highlight (which fires selectionchange → updateGutterPosition)
  // and the subsequent click handler that activates the comment. Without this,
  // the buttons appear for one frame because activeCommentId hasn't been set yet.
  const activateWithGuard = useCallback(
    (commentId: string) => {
      storeApi.setState({ activating: true })
      storeApi.getState().setActiveComment(commentId)
      requestAnimationFrame(() => {
        storeApi.setState({ activating: false })
      })
    },
    [storeApi]
  )

  // Reset UI state on mount (selection/cards). Comments themselves are fetched by
  // useCommentThreads via useQuery — no imperative fetch here.
  useEffect(() => {
    storeApi.getState().init(currentUser.id, currentUser.displayName)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps -- init only needs to fire once per mount

  // Keep the store's mention candidates in sync with the reactive prop (the
  // org-members store loads asynchronously, so this can change after init).
  useEffect(() => {
    storeApi.setState({ mentionableUsers })
  }, [mentionableUsers, storeApi])

  // Observe editor DOM mutations for position updates
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const editor = container.querySelector("[contenteditable]")
    if (!editor) return

    const observer = new MutationObserver(() => schedulePositionUpdate())
    observer.observe(editor, { childList: true, subtree: true, characterData: true })
    return () => observer.disconnect()
  }, [containerRef, schedulePositionUpdate])

  // Helper to get selection range, auto-expanding to block if collapsed
  const getSelectionRange = useEditorEventCallback(view => {
    if (!view) return null
    return getRange(view.state, savedSelectionRef.current)
  })

  // useEditorEventCallback versions for mark operations — needed because
  // the ProseMirror view is only available inside the editor context.

  // Unsaved highlight: local-only decoration, kept out of the shared Yjs doc.
  const addPendingComment = useEditorEventCallback((view, pendingId: string, from: number, to: number) => {
    if (!view) return
    addPendingCommentDecoration(view, pendingId, from, to)
  })

  // On cancel/dismiss, just drop the local decoration — no doc change to broadcast.
  const clearPendingComment = useEditorEventCallback((view, pendingId: string) => {
    if (!view) return
    clearPendingCommentDecoration(view, pendingId)
  })
  useLayoutEffect(() => {
    clearPendingCommentRef.current = clearPendingComment
  }, [clearPendingComment])

  // On save, promote the pending decoration to the real synced `comment` mark.
  const commitPending = useEditorEventCallback((view, pendingId: string) => {
    if (!view) return
    commitPendingComment(view, pendingId)
  })

  // Removes a persisted comment's mark from the shared doc (delete/resolve).
  const removeMark = useEditorEventCallback((view, commentId: string) => {
    if (!view) return
    const markType = view.state.schema.marks.comment
    if (!markType) return
    let tr = view.state.tr
    view.state.doc.descendants((node, pos) => {
      for (const mark of node.marks) {
        if (mark.type === markType && mark.attrs.commentId === commentId) {
          tr = tr.removeMark(pos, pos + node.nodeSize, mark)
        }
      }
    })
    if (tr.docChanged) view.dispatch(tr)
  })

  const handleOpenCommentWithEditor = useCallback(() => {
    const range = getSelectionRange()
    if (!range) return

    savedSelectionRef.current = { from: range.from, to: range.to }
    const pendingId = crypto.randomUUID()

    storeApi.getState().openCommentCard(cursorInfo.top, range.text, pendingId)
    addPendingComment(pendingId, range.from, range.to)
    storeApi.getState().setActiveComment(pendingId)
  }, [getSelectionRange, cursorInfo.top, storeApi, savedSelectionRef, addPendingComment])

  const handleOpenReaction = useCallback(() => {
    const range = getSelectionRange()
    if (!range) return

    savedSelectionRef.current = { from: range.from, to: range.to }
    const pendingId = crypto.randomUUID()

    storeApi.getState().openReactionPicker(range.text, pendingId)
    addPendingComment(pendingId, range.from, range.to)
    storeApi.getState().setActiveComment(pendingId)
  }, [getSelectionRange, savedSelectionRef, storeApi, addPendingComment])

  const handleAddReaction = useCallback(
    async (emoji: string) => {
      const { pendingCommentId, selectedQuotedText, closeReactionPicker, setActiveComment } = storeApi.getState()
      // Save first, then promote the pending decoration to a real mark. createComment
      // patches the cache with the new thread, so by the time the mark lands its id is
      // already a known thread and cleanupOrphanMarks keeps it.
      if (pendingCommentId && selectedQuotedText) {
        await createComment(emoji, selectedQuotedText, pendingCommentId)
        commitPending(pendingCommentId)
      }
      closeReactionPicker()
      setActiveComment(null)
    },
    [storeApi, createComment, commitPending]
  )

  // Click on highlighted text activates/cycles the linked comment
  const handleEditorClick = useEditorEventCallback((view, e: MouseEvent) => {
    if (!view) return
    const target = (e.target as HTMLElement).closest(".inline-comment-highlight[data-comment-id]")
    if (!target) {
      storeApi.setState({ activating: false })
      dismissActiveUI()
      return
    }

    const markType = view.state.schema.marks.comment
    if (!markType) {
      storeApi.getState().setActiveComment(null)
      return
    }

    try {
      const pos = view.posAtDOM(target, 0)
      const node = view.state.doc.resolve(pos).nodeAfter
      const ids = (node?.marks ?? []).filter(m => m.type === markType).map(m => m.attrs.commentId as string)

      if (ids.length <= 1) {
        activateWithGuard(ids[0] ?? target.getAttribute("data-comment-id")!)
      } else {
        const currentActive = storeApi.getState().activeCommentId
        const currentIdx = currentActive ? ids.indexOf(currentActive) : -1
        activateWithGuard(ids[(currentIdx + 1) % ids.length])
      }
    } catch {
      const id = target.getAttribute("data-comment-id")
      if (id) {
        activateWithGuard(id)
      }
    }
  })

  // Mousedown on highlights — set activating to prevent cursor buttons flash
  const handleEditorMouseDown = useEditorEventCallback((_view, e: MouseEvent) => {
    const target = (e.target as HTMLElement).closest(".inline-comment-highlight[data-comment-id]")
    if (target) storeApi.setState({ activating: true })
  })

  // Attach click/mousedown listeners to editor
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const editor = container.querySelector("[contenteditable]")
    if (!editor) return

    const onClick = (e: Event) => handleEditorClick(e as MouseEvent)
    const onMouseDown = (e: Event) => handleEditorMouseDown(e as MouseEvent)
    editor.addEventListener("click", onClick)
    editor.addEventListener("mousedown", onMouseDown)
    return () => {
      editor.removeEventListener("click", onClick)
      editor.removeEventListener("mousedown", onMouseDown)
    }
  }, [containerRef, handleEditorClick, handleEditorMouseDown])

  // Click outside to dismiss. Pop-overs portaled to document.body (mention suggester,
  // reactions picker, comment menu) are tagged with [data-comment-portal] so clicks inside
  // them count as inside the comment system, even though they aren't inside containerRef.
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const container = containerRef.current
      if (!container) return
      const target = e.target as HTMLElement | null
      if (container.contains(target)) return
      if (target?.closest("[data-comment-portal]")) return
      dismissActiveUI()
    }

    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [containerRef, dismissActiveUI])

  // Close reaction picker on Escape
  useEffect(() => {
    if (!showReactionPicker) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismissActiveUI()
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [showReactionPicker, dismissActiveUI])

  // Update active highlight style — creates a <style> element on mount, removes on unmount
  const styleRef = useRef<HTMLStyleElement | null>(null)
  useEffect(() => {
    const style = document.createElement("style")
    style.id = "comment-active-style"
    document.head.appendChild(style)
    styleRef.current = style
    return () => {
      style.remove()
      styleRef.current = null
    }
  }, [])

  useEffect(() => {
    const style = styleRef.current
    if (!style) return
    if (activeCommentId && /^[0-9a-f-]+$/i.test(activeCommentId)) {
      const sel = `[data-comment-id="${activeCommentId}"]`
      const active =
        "background-color: color-mix(in srgb, var(--color-primary) 30%, transparent) !important; border-bottom-color: color-mix(in srgb, var(--color-primary) 60%, transparent) !important;"
      style.textContent = `.inline-comment-highlight${sel} { ${active} } .inline-comment-highlight${sel} .inline-comment-highlight { ${active} }`
    } else {
      style.textContent = ""
    }
  }, [activeCommentId])

  // Reposition when threads change
  useEffect(() => {
    requestAnimationFrame(() => positionGutter())
  }, [threads, positionGutter])

  return (
    <>
      <CommentGutter
        reactions={REACTIONS}
        onOpenComment={handleOpenCommentWithEditor}
        onOpenReaction={handleOpenReaction}
        onAddReaction={handleAddReaction}
        editorFocused={editorFocused}
        cursorBlockHasContent={cursorInfo.blockHasContent}
        cursorTop={cursorInfo.top}
      />
      <CommentCards
        currentUser={currentUser}
        onRemoveMark={removeMark}
        onCommitPendingComment={commitPending}
        onClearPendingComment={clearPendingComment}
      />
    </>
  )
}
