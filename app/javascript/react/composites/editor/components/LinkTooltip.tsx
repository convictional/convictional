import { useEditorEffect } from "@handlewithcare/react-prosemirror"
import { useState } from "react"

import { Tooltip } from "~/react/ui/Tooltip"
import { isValidHref } from "../features/linkUrls"
import type { LinkTooltipActions, LinkTooltipState } from "../features/useLinkTooltip"
import { useLinkTooltipState } from "../features/useLinkTooltip"

export function LinkTooltip() {
  // useEditorState throws if called before the EditorView is initialized.
  // Defer rendering until the view is ready via useEditorEffect.
  const [ready, setReady] = useState(false)
  useEditorEffect(() => {
    setReady(true)
  }, [])

  if (!ready) return null
  return <LinkTooltipInner />
}

function LinkTooltipInner() {
  const { state, actions } = useLinkTooltipState()
  if (!state.visible) return null
  return <LinkTooltipBody state={state} actions={actions} />
}

export function LinkTooltipBody({ state, actions }: { state: LinkTooltipState; actions: LinkTooltipActions }) {
  const { linkInfo, tooltipRef } = state
  const { updateLink, removeLink } = actions

  const [mode, setMode] = useState<"view" | "edit">("view")
  const [editUrl, setEditUrl] = useState("")

  const [prevHref, setPrevHref] = useState<string | null>(null)
  if (linkInfo && linkInfo.href !== prevHref) {
    setPrevHref(linkInfo.href)
    setEditUrl(linkInfo.href)
    setMode("view")
  } else if (!linkInfo && prevHref !== null) {
    setPrevHref(null)
  }

  if (!linkInfo) return null

  return (
    <div ref={tooltipRef} className="absolute z-50 floating-card !p-2 flex items-center gap-2 text-sm">
      {mode === "view" ? (
        <>
          <span className="text-xs truncate max-w-48 text-base-content/70">{linkInfo.href}</span>
          <div className="join join-horizontal">
            <Tooltip content="Open link">
              <a
                href={linkInfo.href}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-sm btn-square join-item"
                onMouseDown={e => e.preventDefault()}
              >
                <span className="material-symbols-outlined text-lg">open_in_new</span>
              </a>
            </Tooltip>
            <Tooltip content="Edit link">
              <button
                type="button"
                className="btn btn-sm btn-square join-item"
                onMouseDown={e => e.preventDefault()}
                onClick={() => {
                  setEditUrl(linkInfo.href)
                  setMode("edit")
                }}
              >
                <span className="material-symbols-outlined text-lg">edit</span>
              </button>
            </Tooltip>
            <Tooltip content="Unlink">
              <button
                type="button"
                className="btn btn-sm btn-square join-item"
                onMouseDown={e => e.preventDefault()}
                onClick={() => removeLink()}
              >
                <span className="material-symbols-outlined text-lg">link_off</span>
              </button>
            </Tooltip>
          </div>
        </>
      ) : (
        <>
          <input
            type="text"
            value={editUrl}
            onChange={e => setEditUrl(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter") {
                e.preventDefault()
                if (isValidHref(editUrl)) updateLink(editUrl)
              } else if (e.key === "Escape") {
                e.preventDefault()
                e.stopPropagation()
                setMode("view")
              }
            }}
            className="input input-sm w-56"
            placeholder="https://..."
          />
          <div className="join join-horizontal">
            <button
              type="button"
              className="btn btn-sm btn-primary join-item"
              disabled={!isValidHref(editUrl)}
              onMouseDown={e => e.preventDefault()}
              onClick={() => updateLink(editUrl)}
            >
              Save
            </button>
            <button
              type="button"
              className="btn btn-sm join-item"
              onMouseDown={e => e.preventDefault()}
              onClick={() => setMode("view")}
            >
              Cancel
            </button>
          </div>
        </>
      )}
    </div>
  )
}
