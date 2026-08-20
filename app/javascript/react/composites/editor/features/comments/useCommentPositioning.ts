import { useEditorEffect, useEditorEventCallback } from "@handlewithcare/react-prosemirror"
import { NodeSelection } from "prosemirror-state"
import { useCallback, useEffect, useRef, useState } from "react"

import { COLLAPSED_SECTION_CLASS } from "~/react/composites/editor/features/collapsibleHeadings"
import { useCommentStore, useCommentStoreApi } from "./CommentStoreContext"

export interface CursorInfo {
  top: number
  blockHasContent: boolean
}

// Pure direction decision so it can be unit-tested without jsdom layout. Returns "up"
// only when the card would overflow the viewport bottom AND there's more room above the
// mark than below — otherwise we keep the default downward growth.
export function pickCardDirection(
  markRect: { top: number; bottom: number },
  cardHeight: number,
  viewportHeight: number,
  topClampOffset: number = 0
): "up" | "down" {
  const spaceBelow = viewportHeight - markRect.bottom
  const spaceAbove = markRect.top - topClampOffset
  return cardHeight > spaceBelow && spaceAbove > spaceBelow ? "up" : "down"
}

// Keyed off the selection anchor rather than document.activeElement to avoid the
// mousedown→focus→selectionchange timing race.
export function isSelectionInsideEditor(editorDom: Node | null, anchorNode: Node | null): boolean {
  if (!editorDom || !anchorNode) return false
  return editorDom.contains(anchorNode)
}

// The element whose vertical geometry a comment marker should anchor to. Normally the
// highlight span itself, but a span inside a collapsed heading section has display:none
// and therefore an all-zero getBoundingClientRect — anchoring to it would slam every
// hidden marker to the top of the editor. In that case we anchor to the section heading
// (the nearest earlier top-level block that isn't itself collapsed) so the marker sits
// beside the collapsed heading. Returns null only if a collapsed mark has no heading
// before it, which shouldn't happen but is guarded so the marker is hidden rather than
// mispositioned.
export function markAnchorElement(mark: Element): Element | null {
  const collapsedBlock = mark.closest(`.${COLLAPSED_SECTION_CLASS}`)
  if (!collapsedBlock) return mark

  let heading = collapsedBlock.previousElementSibling
  while (heading && heading.classList.contains(COLLAPSED_SECTION_CLASS)) {
    heading = heading.previousElementSibling
  }
  return heading
}

// No clamp — the card tracks its mark 1:1 under scroll, including sliding behind the sticky header.
export function computeActiveCardTop(
  markRect: { top: number; bottom: number },
  containerTop: number,
  cardHeight: number,
  direction: "up" | "down"
): number {
  if (direction === "up") return markRect.bottom - containerTop - cardHeight
  return markRect.top - containerTop
}

export function useCommentPositioning(containerRef: React.RefObject<HTMLDivElement | null>) {
  const [editorFocused, setEditorFocused] = useState(false)
  const [cursorInfo, setCursorInfo] = useState<CursorInfo>({ top: 0, blockHasContent: false })
  const savedSelectionRef = useRef<{ from: number; to: number }>({ from: 0, to: 0 })
  const positionFrameRef = useRef<number | null>(null)
  const stickyHeaderRef = useRef<HTMLElement | null | undefined>(undefined)

  const storeApi = useCommentStoreApi()
  const activeCommentId = useCommentStore(s => s.activeCommentId)
  const showCommentCard = useCommentStore(s => s.showCommentCard)
  const showReactionPicker = useCommentStore(s => s.showReactionPicker)

  // Drop-direction is decided once when the active card opens and held for the lifetime
  // of that open card so the card doesn't flip sides mid-typing as its height grows.
  const cardDirectionRef = useRef<"up" | "down" | null>(null)

  // Update gutter position from editor selection changes
  const updateGutterPosition = useEditorEventCallback(view => {
    if (!view || !containerRef.current) return

    // Bail when the selection is inside a comment card's nested editor, not the outer
    // body: otherwise the setState below re-renders the nested editor, whose controlled
    // commit reasserts a stale selection and snaps the caret to the start (issue #8826).
    const domSel = window.getSelection()
    if (!isSelectionInsideEditor(view.dom, domSel?.anchorNode ?? null)) return

    setEditorFocused(view.hasFocus())

    if (!domSel || !domSel.rangeCount) return
    const range = domSel.getRangeAt(0)
    const rect = range.getBoundingClientRect()
    const containerRect = containerRef.current.getBoundingClientRect()
    if (rect.top === 0 && rect.left === 0) {
      setCursorInfo({ top: 0, blockHasContent: false })
      return
    }

    const top = rect.top - containerRect.top
    let blockHasContent = false

    const posInfo = view.posAtCoords({ left: rect.left + 1, top: rect.top + 1 })
    if (posInfo) {
      const $resolved = view.state.doc.resolve(posInfo.pos)
      const sel = view.state.selection
      blockHasContent =
        !domSel.isCollapsed ||
        $resolved.parent.textContent.length > 0 ||
        (sel instanceof NodeSelection && sel.node.type.name === "image")
    }

    setCursorInfo({ top, blockHasContent })

    if (view.hasFocus()) {
      const sel = view.state.selection
      savedSelectionRef.current = { from: sel.from, to: sel.to }
    }
  })

  // Listen for selection changes and focus events
  useEditorEffect(
    view => {
      const editor = view.dom
      if (!editor) return

      const onSelectionChange = () => updateGutterPosition()
      const onFocusIn = () => setEditorFocused(true)
      const onFocusOut = () => {
        requestAnimationFrame(() => {
          const active = document.activeElement
          const inGutter = !!active?.closest("[data-comment-gutter-actions], [data-comment-gutter-avatars]")
          if (!view.hasFocus() && !inGutter) setEditorFocused(false)
        })
      }

      document.addEventListener("selectionchange", onSelectionChange)
      editor.addEventListener("focusin", onFocusIn)
      editor.addEventListener("focusout", onFocusOut)

      return () => {
        document.removeEventListener("selectionchange", onSelectionChange)
        editor.removeEventListener("focusin", onFocusIn)
        editor.removeEventListener("focusout", onFocusOut)
      }
    },
    [updateGutterPosition]
  )

  // Position gutter items (avatars + cursor buttons) without overlap
  const positionGutter = useCallback(() => {
    const container = containerRef.current
    if (!container) return
    const containerRect = container.getBoundingClientRect()

    // The sticky header lives outside the comment container's DOM subtree,
    // so we traverse up once and cache the element to avoid repeated tree walks.
    if (stickyHeaderRef.current === undefined) {
      stickyHeaderRef.current =
        container
          .closest("#document-editor, #post-draft")
          ?.parentElement?.querySelector<HTMLElement>(":scope > .sticky") ?? null
    }

    const items: { el: HTMLElement; anchorTop: number; height: number }[] = []

    // Avatars — anchored to their inline marks
    const avatarEls = container.querySelectorAll<HTMLElement>("[data-comment-gutter-avatars] [data-avatar-for]")
    const avatarsByLine: { el: HTMLElement; anchorTop: number }[] = []
    avatarEls.forEach(el => {
      if (el.style.display === "none") return
      const markId = el.getAttribute("data-avatar-for")
      const mark = container.querySelector(`[data-comment-id=${JSON.stringify(markId)}]`)
      const anchor = mark && markAnchorElement(mark)
      if (!anchor) {
        el.style.visibility = "hidden"
        return
      }
      el.style.visibility = ""
      const anchorTop = anchor.getBoundingClientRect().top - containerRect.top
      avatarsByLine.push({ el, anchorTop })
    })

    // Group avatars by line (within 4px = same line)
    const lineGroups: (typeof avatarsByLine)[] = []
    for (const av of avatarsByLine) {
      const existing = lineGroups.find(g => Math.abs(g[0].anchorTop - av.anchorTop) < 4)
      if (existing) existing.push(av)
      else lineGroups.push([av])
    }

    const multiGroups: { group: typeof avatarsByLine; anchorTop: number }[] = []
    for (const group of lineGroups) {
      if (group.length === 1) {
        group[0].el.style.left = ""
        group[0].el.style.zIndex = ""
        items.push({ el: group[0].el, anchorTop: group[0].anchorTop, height: 32 })
      } else {
        items.push({ el: group[0].el, anchorTop: group[0].anchorTop, height: 32 })
        multiGroups.push({ group, anchorTop: group[0].anchorTop })
      }
    }

    // Cursor buttons
    const cursorEl = container.querySelector<HTMLElement>("[data-gutter-cursor]")
    if (
      cursorEl &&
      editorFocused &&
      cursorInfo.blockHasContent &&
      !showCommentCard &&
      !showReactionPicker &&
      !activeCommentId
    ) {
      items.push({ el: cursorEl, anchorTop: cursorInfo.top, height: (cursorEl.offsetHeight || 72) + 8 })
    }

    // Sort and stack without overlap
    items.sort((a, b) => a.anchorTop - b.anchorTop)
    let prevBottom = 0
    let prevIsCursor = false
    for (const item of items) {
      const isCursor = item.el === cursorEl
      const gap = prevBottom > 0 && (prevIsCursor || isCursor) ? 8 : 4
      const finalTop = Math.max(item.anchorTop, prevBottom)
      item.el.style.top = finalTop + "px"
      prevBottom = finalTop + item.height + gap
      prevIsCursor = isCursor
    }

    // Horizontal overlap for multi-avatar groups
    for (const { group } of multiGroups) {
      const finalTop = group[0].el.style.top
      const step = 14
      for (let i = 0; i < group.length; i++) {
        group[i].el.style.top = finalTop
        group[i].el.style.left = i * step + "px"
        group[i].el.style.zIndex = String(group.length - i)
      }
    }

    // Position active comment card. Direction is sticky-on-open: decided on the first
    // positionGutter call after activeCommentId changes, then reused so the card doesn't
    // flip while the user types and the card grows.
    if (activeCommentId) {
      const cardEl = container.querySelector<HTMLElement>(
        `[data-comment-cards] [data-for-comment-id=${JSON.stringify(activeCommentId)}]`
      )
      const mark = container.querySelector(`[data-comment-id=${JSON.stringify(activeCommentId)}]`)
      const anchor = mark && markAnchorElement(mark)
      if (cardEl && anchor) {
        const markRect = anchor.getBoundingClientRect()
        const cardHeight = cardEl.offsetHeight
        if (cardDirectionRef.current === null) {
          // stickyHeaderViewportBottom is in viewport coords for pickCardDirection.
          const stickyHeaderViewportBottom = stickyHeaderRef.current
            ? stickyHeaderRef.current.getBoundingClientRect().bottom + 8
            : 0
          cardDirectionRef.current = pickCardDirection(
            markRect,
            cardHeight,
            window.innerHeight,
            stickyHeaderViewportBottom
          )
        }
        const top = computeActiveCardTop(markRect, containerRect.top, cardHeight, cardDirectionRef.current)
        cardEl.style.top = top + "px"
      }
    }

    // Position new comment form — write to DOM directly (like the active card
    // above) so the store retains the original cursor-anchored position.
    const formEl = container.querySelector<HTMLElement>("[data-comment-form]")
    if (formEl && showCommentCard) {
      formEl.style.top = storeApi.getState().commentCardTop + "px"
    }

    // Clamp comment cards container to viewport
    const cardsEl = container.querySelector<HTMLElement>("[data-comment-cards]")
    if (cardsEl) {
      cardsEl.style.transform = ""
      const r = cardsEl.getBoundingClientRect()
      const overflow = r.right - window.innerWidth + 8
      cardsEl.style.transform = overflow > 0 ? `translateX(-${overflow}px)` : ""
    }
  }, [containerRef, editorFocused, cursorInfo, activeCommentId, showCommentCard, showReactionPicker, storeApi])

  // Schedule position updates via rAF
  const schedulePositionUpdate = useCallback(() => {
    if (positionFrameRef.current) return
    positionFrameRef.current = requestAnimationFrame(() => {
      positionFrameRef.current = null
      positionGutter()
    })
  }, [positionGutter])

  // Reposition on window resize and scroll
  useEffect(() => {
    window.addEventListener("resize", schedulePositionUpdate)
    window.addEventListener("scroll", schedulePositionUpdate, { passive: true })
    return () => {
      window.removeEventListener("resize", schedulePositionUpdate)
      window.removeEventListener("scroll", schedulePositionUpdate)
      if (positionFrameRef.current) {
        cancelAnimationFrame(positionFrameRef.current)
        positionFrameRef.current = null
      }
    }
  }, [schedulePositionUpdate])

  // Reposition when active comment or threads change. Reset the sticky direction so the
  // newly opened card decides its own direction from current viewport geometry.
  useEffect(() => {
    cardDirectionRef.current = null
    requestAnimationFrame(() => positionGutter())
  }, [activeCommentId, positionGutter])

  return {
    editorFocused,
    cursorInfo,
    savedSelectionRef,
    positionGutter,
    schedulePositionUpdate,
  }
}
