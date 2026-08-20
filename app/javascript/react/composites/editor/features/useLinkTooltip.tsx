import { computePosition, flip, offset } from "@floating-ui/dom"
import { useEditorEffect, useEditorEventCallback, useEditorState } from "@handlewithcare/react-prosemirror"
import type { Node } from "prosemirror-model"
import { Plugin, PluginKey } from "prosemirror-state"
import { findDomRefAtPos } from "prosemirror-utils"
import type { EditorView } from "prosemirror-view"
import { useMemo, useRef, useState } from "react"

import { schema } from "~/richText/schema"
import type { EditorFeature } from "../types"
import { isValidHref } from "./linkUrls"

export interface LinkInfo {
  from: number
  to: number
  href: string
}

// O(depth + sibling count) — walks only the parent node's children instead of
// the full document tree. Called on every selection change.
export function findLinkAtDocPos(doc: Node, pos: number): LinkInfo | null {
  const $pos = doc.resolve(pos)
  const parent = $pos.parent
  const parentStart = $pos.start()
  let nodeStart = parentStart
  for (let i = 0; i < parent.childCount; i++) {
    const child = parent.child(i)
    const nodeEnd = nodeStart + child.nodeSize
    if (pos >= nodeStart && pos <= nodeEnd) {
      const linkMark = schema.marks.link.isInSet(child.marks)
      if (linkMark) {
        return { from: nodeStart, to: nodeEnd, href: linkMark.attrs.href as string }
      }
    }
    nodeStart = nodeEnd
  }
  return null
}

export function findLinkAtCursor(state: import("prosemirror-state").EditorState): LinkInfo | null {
  const { from, to } = state.selection
  if (from !== to) return null
  return findLinkAtDocPos(state.doc, from)
}

export const linkClickPluginKey = new PluginKey<LinkInfo | null>("linkClick")

export function handleLinkClickEvent(view: EditorView, event: MouseEvent): boolean {
  const anchor = (event.target as HTMLElement | null)?.closest("a")
  if (!anchor) return false
  if (!view.dom.contains(anchor)) return false
  if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey || event.button !== 0) return false
  let pos: number
  try {
    pos = view.posAtDOM(anchor, 0)
  } catch {
    return false
  }
  const info = findLinkAtDocPos(view.state.doc, pos)
  if (!info) return false
  event.preventDefault()
  view.dispatch(view.state.tr.setMeta(linkClickPluginKey, info))
  return true
}

export function createLinkClickPlugin(): Plugin<LinkInfo | null> {
  return new Plugin<LinkInfo | null>({
    key: linkClickPluginKey,
    state: {
      init() {
        return null
      },
      apply(tr, value) {
        const meta = tr.getMeta(linkClickPluginKey)
        if (meta !== undefined) return meta
        if (tr.docChanged) return null
        if (value !== null && (tr.selection.anchor < value.from || tr.selection.anchor > value.to)) return null
        return value
      },
    },
    props: {
      handleDOMEvents: {
        click(view, event) {
          return handleLinkClickEvent(view, event)
        },
      },
    },
  })
}

export interface LinkTooltipActions {
  updateLink: (href: string) => void
  removeLink: () => void
}

export interface LinkTooltipState {
  linkInfo: LinkInfo | null
  visible: boolean
  tooltipRef: React.RefObject<HTMLDivElement | null>
}

// Called outside <Editor> — returns plugins only.
export function useLinkTooltip(): EditorFeature {
  const plugin = useMemo(() => createLinkClickPlugin(), [])
  return { plugins: [plugin] }
}

// Must be called inside <Editor> children (requires ProseMirror context).
// Provides link detection, positioning, and edit/remove operations.
export function useLinkTooltipState(): { state: LinkTooltipState; actions: LinkTooltipActions } {
  const editorState = useEditorState()
  const [isKeyboardNav, setIsKeyboardNav] = useState(false)
  const tooltipRef = useRef<HTMLDivElement>(null)

  const activeLinkRef = useRef<LinkInfo | null>(null)

  useEditorEffect(view => {
    const handleMouseDown = () => setIsKeyboardNav(false)

    const handleKeyDown = (e: Event) => {
      const navKeys = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Tab", "Home", "End", "PageUp", "PageDown"]
      setIsKeyboardNav(navKeys.includes((e as KeyboardEvent).key))
    }

    const handleBlur = (e: Event) => {
      // Don't dismiss if focus moved into the tooltip (e.g. clicking the URL
      // input or remove button). Safari may report relatedTarget as null for
      // button clicks, so also check after a microtask.
      const related = (e as FocusEvent).relatedTarget as HTMLElement | null
      if (related && tooltipRef.current?.contains(related)) return
      requestAnimationFrame(() => {
        if (tooltipRef.current?.contains(document.activeElement)) return
        activeLinkRef.current = null
      })
    }

    const handleOutsideMouseDown = (event: MouseEvent) => {
      if (!linkClickPluginKey.getState(view.state)) return
      const target = event.target as globalThis.Node | null
      if (target && tooltipRef.current?.contains(target)) return
      if (target && view.dom.contains(target)) return
      view.dispatch(view.state.tr.setMeta(linkClickPluginKey, null))
    }

    const handleDocumentKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return
      if (!linkClickPluginKey.getState(view.state)) return
      view.dispatch(view.state.tr.setMeta(linkClickPluginKey, null))
    }

    view.dom.addEventListener("mousedown", handleMouseDown)
    view.dom.addEventListener("keydown", handleKeyDown)
    view.dom.addEventListener("blur", handleBlur, true)
    document.addEventListener("mousedown", handleOutsideMouseDown)
    document.addEventListener("keydown", handleDocumentKeyDown)

    return () => {
      view.dom.removeEventListener("mousedown", handleMouseDown)
      view.dom.removeEventListener("keydown", handleKeyDown)
      view.dom.removeEventListener("blur", handleBlur, true)
      document.removeEventListener("mousedown", handleOutsideMouseDown)
      document.removeEventListener("keydown", handleDocumentKeyDown)
    }
  }, [])

  const { from: selFrom, to: selTo } = editorState.selection
  const clickState = linkClickPluginKey.getState(editorState) ?? null
  const found = findLinkAtCursor(editorState)
  const activeLink = clickState ?? found
  const visible = !!clickState || (!!found && !isKeyboardNav)

  useEditorEffect(
    view => {
      if (activeLink && visible) {
        activeLinkRef.current = activeLink

        if (tooltipRef.current) {
          const domEl = findDomRefAtPos(activeLink.from, view.domAtPos.bind(view))
          computePosition(domEl as Element, tooltipRef.current, {
            placement: "bottom-start",
            middleware: [offset(6), flip()],
          }).then(({ x, y }) => {
            if (tooltipRef.current) {
              tooltipRef.current.style.left = `${x}px`
              tooltipRef.current.style.top = `${y}px`
            }
          })
        }
      } else {
        activeLinkRef.current = null
      }
    },
    [selFrom, selTo, isKeyboardNav, activeLink?.from, activeLink?.href]
  )

  const updateLink = useEditorEventCallback((view, href: string) => {
    const info = activeLinkRef.current
    if (!info) return
    if (!isValidHref(href)) return

    view.dispatch(
      view.state.tr
        .addMark(info.from, info.to, schema.marks.link.create({ href: href.trim() }))
        .setMeta(linkClickPluginKey, null)
    )
  })

  // Use onMouseDown instead of onClick so it fires before blur clears activeLinkRef
  const removeLink = useEditorEventCallback(view => {
    const info = activeLinkRef.current
    if (!info) return
    view.dispatch(view.state.tr.removeMark(info.from, info.to, schema.marks.link).setMeta(linkClickPluginKey, null))
    activeLinkRef.current = null
    view.focus()
  })

  return {
    state: { linkInfo: activeLink, visible, tooltipRef },
    actions: { updateLink, removeLink },
  }
}
