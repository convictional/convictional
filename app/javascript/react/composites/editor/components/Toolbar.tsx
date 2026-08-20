import { useEditorEffect, useEditorEventCallback } from "@handlewithcare/react-prosemirror"
import { toggleMark, wrapIn } from "prosemirror-commands"
import { NodeType } from "prosemirror-model"
import { useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"

import { toggleCode, toggleHeading } from "~/richText/commands"
import { schema } from "~/richText/schema"
import { toggleList, toggleTaskList } from "~/richText/schema/keymap"
import { detectLinkHref } from "../features/linkUrls"
import { type AttachmentsFeature, openFilePickerAndUpload } from "../features/useAttachments"
import { useEditorActions } from "../useEditorActions"
import type { KlipyGif } from "./GifPicker"
import { GifPicker } from "./GifPicker"
import { LinkDialog } from "./LinkDialog"
import { TableDialog } from "./TableDialog"
import { ToolbarGroup } from "./ToolbarGroup"
import { ToolButton } from "./ToolButton"

export type ToolbarTool =
  | "bold"
  | "italic"
  | "code"
  | "strikethrough"
  | "heading"
  | "quote"
  | "bulletList"
  | "orderedList"
  | "taskList"
  | "link"
  | "image"

interface ToolbarProps {
  hasKlipy: boolean
  klipyApiKey: string | null
  // Gates only the "Insert table" affordance. In-table editing (add/delete
  // row/column) is always available when the caret is inside a table,
  // regardless of this flag — pasted tables remain editable everywhere.
  enableTableInsert?: boolean
  portalTarget?: HTMLElement | null
  onToggleZen?: () => void
  // When provided, only renders buttons for the listed tools. Defaults to all tools.
  tools?: readonly ToolbarTool[]
  // When true, groups tools into dropdown menus (Paragraph, List, Insert)
  // with Bold/Italic kept as individual buttons. Fits in a single row.
  grouped?: boolean
  // The editor's attachments feature. Required for the "image" tool to render
  // as an attach-file button; without it the button is omitted.
  attachments?: AttachmentsFeature
}

export function Toolbar({
  hasKlipy,
  klipyApiKey,
  enableTableInsert,
  portalTarget,
  onToggleZen,
  tools,
  grouped,
  attachments,
}: ToolbarProps) {
  // useEditorState throws if called before the EditorView is initialized.
  // Defer rendering until the view is ready via useEditorEffect.
  const [ready, setReady] = useState(false)
  useEditorEffect(() => {
    setReady(true)
  }, [])

  if (!ready) return null

  const content = (
    <ToolbarContent
      hasKlipy={hasKlipy}
      klipyApiKey={klipyApiKey}
      enableTableInsert={enableTableInsert}
      onToggleZen={onToggleZen}
      tools={tools}
      grouped={grouped}
      attachments={attachments}
    />
  )
  return portalTarget ? createPortal(content, portalTarget) : content
}

function ToolbarContent({
  hasKlipy,
  klipyApiKey,
  enableTableInsert,
  onToggleZen,
  tools,
  grouped,
  attachments,
}: ToolbarProps) {
  const shows = (tool: ToolbarTool) => tools === undefined || tools.includes(tool)
  const [linkDialogOpen, setLinkDialogOpen] = useState(false)
  // Freeze the dialog's mode at open time so caret movement after opening doesn't
  // flip the popover between Insert-table and in-table-ops — otherwise a user who
  // opened the ops popover and then clicked outside the table would see an
  // Insert-table button and accidentally insert a new one.
  const [tableDialog, setTableDialog] = useState<{ open: boolean; inTable: boolean }>({ open: false, inTable: false })
  const tableWrapperRef = useRef<HTMLDivElement>(null)
  const linkAnchorRef = useRef<HTMLDivElement>(null)
  const [linkDefaultUrl, setLinkDefaultUrl] = useState("")

  // Close the table popover on click outside or Escape.
  useEffect(() => {
    if (!tableDialog.open) return

    const handleClick = (e: MouseEvent) => {
      if (tableWrapperRef.current && !tableWrapperRef.current.contains(e.target as Node)) {
        setTableDialog(prev => ({ ...prev, open: false }))
      }
    }
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setTableDialog(prev => ({ ...prev, open: false }))
    }

    // Delay to avoid catching the open click itself.
    const timer = setTimeout(() => {
      window.addEventListener("click", handleClick)
      window.addEventListener("keydown", handleEscape)
    }, 0)
    return () => {
      clearTimeout(timer)
      window.removeEventListener("click", handleClick)
      window.removeEventListener("keydown", handleEscape)
    }
  }, [tableDialog.open])

  const actions = useEditorActions()
  const { runCmd, canRunCmd, applyLink, insertImage, isMarkActive, getHeadingLevel, hasAncestorOfType } = actions

  // Opens the native file picker and uploads through the attachments feature.
  // Called unconditionally (rules of hooks); the guard inside is a no-op when no
  // attachments feature is wired.
  const triggerAttach = useEditorEventCallback(view => {
    if (attachments) openFilePickerAndUpload(view, attachments)
  })

  const inTable = hasAncestorOfType(schema.nodes.table)

  const openLinkDialog = () => {
    if (isMarkActive(schema.marks.link)) {
      runCmd(toggleMark(schema.marks.link))
      return
    }
    const sel = actions.lastSelectionRef.current
    if (sel.from === sel.to) return

    setLinkDefaultUrl(detectLinkHref(sel.text))
    setLinkDialogOpen(true)
  }

  const handleApplyLink = (href: string) => {
    applyLink(href)
    setLinkDialogOpen(false)
  }

  const handleSelectGif = (gif: KlipyGif) => {
    insertImage(gif.content_url, gif.title)
  }

  const headingLevel = getHeadingLevel()

  const hasActiveBlock = headingLevel !== undefined || hasAncestorOfType(schema.nodes.blockquote)
  const hasActiveList =
    hasAncestorOfType(schema.nodes.bullet_list) ||
    hasAncestorOfType(schema.nodes.ordered_list) ||
    hasAncestorOfType(schema.nodes.task_list_item)

  if (grouped) {
    return (
      <div className="toolbar-joined flex">
        {shows("bold") && (
          <ToolButton
            icon="format_bold"
            title="Bold"
            active={isMarkActive(schema.marks.strong)}
            onMouseDown={() => runCmd(toggleMark(schema.marks.strong))}
          />
        )}
        {shows("italic") && (
          <ToolButton
            icon="format_italic"
            title="Italic"
            active={isMarkActive(schema.marks.em)}
            onMouseDown={() => runCmd(toggleMark(schema.marks.em))}
          />
        )}
        <ToolbarGroup icon="format_paragraph" label="Paragraph style" active={hasActiveBlock}>
          {shows("heading") && (
            <>
              <ToolButton
                icon="looks_one"
                title="Heading 1"
                className="btn-ghost"
                active={headingLevel === 1}
                onMouseDown={() => runCmd(toggleHeading(1))}
              />
              <ToolButton
                icon="looks_two"
                title="Heading 2"
                className="btn-ghost"
                active={headingLevel === 2}
                onMouseDown={() => runCmd(toggleHeading(2))}
              />
              <ToolButton
                icon="looks_3"
                title="Heading 3"
                className="btn-ghost"
                active={headingLevel === 3}
                onMouseDown={() => runCmd(toggleHeading(3))}
              />
            </>
          )}
          {shows("quote") && (
            <ToolButton
              icon="format_quote"
              title="Quote"
              className="btn-ghost"
              active={hasAncestorOfType(schema.nodes.blockquote)}
              disabled={!canRunCmd(wrapIn(schema.nodes.blockquote))}
              onMouseDown={() => runCmd(wrapIn(schema.nodes.blockquote))}
            />
          )}
          {shows("code") && (
            <ToolButton
              icon="code"
              title="Code"
              className="btn-ghost"
              active={isMarkActive(schema.marks.code) || hasAncestorOfType(schema.nodes.code_block)}
              onMouseDown={() => runCmd(toggleCode())}
            />
          )}
          {shows("strikethrough") && (
            <ToolButton
              icon="format_strikethrough"
              title="Strikethrough"
              className="btn-ghost"
              active={isMarkActive(schema.marks.strikethrough)}
              onMouseDown={() => runCmd(toggleMark(schema.marks.strikethrough))}
            />
          )}
        </ToolbarGroup>
        <ToolbarGroup icon="format_list_bulleted" label="Lists" active={hasActiveList}>
          {shows("bulletList") && (
            <ToolButton
              icon="format_list_bulleted"
              title="Bullet list"
              className="btn-ghost"
              active={hasAncestorOfType(schema.nodes.bullet_list) && !hasAncestorOfType(schema.nodes.task_list_item)}
              onMouseDown={() =>
                runCmd(toggleList(schema.nodes.bullet_list as NodeType, schema.nodes.regular_list_item as NodeType))
              }
            />
          )}
          {shows("orderedList") && (
            <ToolButton
              icon="format_list_numbered"
              title="Numbered list"
              className="btn-ghost"
              active={hasAncestorOfType(schema.nodes.ordered_list)}
              onMouseDown={() =>
                runCmd(toggleList(schema.nodes.ordered_list as NodeType, schema.nodes.regular_list_item as NodeType))
              }
            />
          )}
          {shows("taskList") && (
            <ToolButton
              icon="check_box"
              title="Task list"
              className="btn-ghost"
              active={hasAncestorOfType(schema.nodes.task_list_item)}
              onMouseDown={() => runCmd(toggleTaskList)}
            />
          )}
        </ToolbarGroup>
        <ToolbarGroup icon="add" label="Insert">
          {shows("link") && (
            <div ref={linkAnchorRef} className="relative">
              <ToolButton
                icon="link"
                title="Link"
                className="btn-ghost"
                active={linkDialogOpen}
                disabled={
                  !isMarkActive(schema.marks.link) &&
                  actions.lastSelectionRef.current.from === actions.lastSelectionRef.current.to
                }
                onMouseDown={openLinkDialog}
              />
              {linkDialogOpen && (
                <LinkDialog
                  anchorRef={linkAnchorRef}
                  defaultUrl={linkDefaultUrl}
                  onApply={handleApplyLink}
                  onCancel={() => setLinkDialogOpen(false)}
                />
              )}
            </div>
          )}
          {shows("image") && attachments && (
            <ToolButton icon="attach_file" title="Attach file" className="btn-ghost" onMouseDown={triggerAttach} />
          )}
          {hasKlipy && klipyApiKey && (
            <div className="relative">
              <GifPicker klipyApiKey={klipyApiKey} onSelectGif={handleSelectGif} buttonClassName="btn-ghost" />
            </div>
          )}
          {(enableTableInsert || inTable) && (
            <div ref={tableWrapperRef} className="relative">
              <ToolButton
                icon="table"
                title={inTable ? "Table options" : "Insert table"}
                className="btn-ghost"
                active={tableDialog.open || inTable}
                onMouseDown={() =>
                  setTableDialog(prev => (prev.open ? { ...prev, open: false } : { open: true, inTable }))
                }
              />
              {tableDialog.open && (
                <TableDialog
                  inTable={tableDialog.inTable}
                  onClose={() => setTableDialog(prev => ({ ...prev, open: false }))}
                />
              )}
            </div>
          )}
        </ToolbarGroup>
        {onToggleZen && <ToolButton icon="open_in_full" title="Zen mode" onMouseDown={onToggleZen} />}
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-1">
      {shows("bold") && (
        <ToolButton
          icon="format_bold"
          title="Bold"
          className="btn-ghost"
          active={isMarkActive(schema.marks.strong)}
          onMouseDown={() => runCmd(toggleMark(schema.marks.strong))}
        />
      )}
      {shows("italic") && (
        <ToolButton
          icon="format_italic"
          title="Italic"
          className="btn-ghost"
          active={isMarkActive(schema.marks.em)}
          onMouseDown={() => runCmd(toggleMark(schema.marks.em))}
        />
      )}
      {shows("code") && (
        <ToolButton
          icon="code"
          title="Code"
          className="btn-ghost"
          active={isMarkActive(schema.marks.code) || hasAncestorOfType(schema.nodes.code_block)}
          onMouseDown={() => runCmd(toggleCode())}
        />
      )}
      {shows("strikethrough") && (
        <ToolButton
          icon="format_strikethrough"
          title="Strikethrough"
          className="btn-ghost"
          active={isMarkActive(schema.marks.strikethrough)}
          onMouseDown={() => runCmd(toggleMark(schema.marks.strikethrough))}
        />
      )}
      {shows("heading") && (
        <>
          <ToolButton
            icon="looks_one"
            title="Heading 1"
            className="btn-ghost"
            active={headingLevel === 1}
            onMouseDown={() => runCmd(toggleHeading(1))}
          />
          <ToolButton
            icon="looks_two"
            title="Heading 2"
            className="btn-ghost"
            active={headingLevel === 2}
            onMouseDown={() => runCmd(toggleHeading(2))}
          />
          <ToolButton
            icon="looks_3"
            title="Heading 3"
            className="btn-ghost"
            active={headingLevel === 3}
            onMouseDown={() => runCmd(toggleHeading(3))}
          />
        </>
      )}
      {shows("quote") && (
        <ToolButton
          icon="format_quote"
          title="Quote"
          className="btn-ghost"
          active={hasAncestorOfType(schema.nodes.blockquote)}
          disabled={!canRunCmd(wrapIn(schema.nodes.blockquote))}
          onMouseDown={() => runCmd(wrapIn(schema.nodes.blockquote))}
        />
      )}
      {shows("bulletList") && (
        <ToolButton
          icon="format_list_bulleted"
          title="Bullet list"
          className="btn-ghost"
          active={hasAncestorOfType(schema.nodes.bullet_list) && !hasAncestorOfType(schema.nodes.task_list_item)}
          onMouseDown={() =>
            runCmd(toggleList(schema.nodes.bullet_list as NodeType, schema.nodes.regular_list_item as NodeType))
          }
        />
      )}
      {shows("orderedList") && (
        <ToolButton
          icon="format_list_numbered"
          title="Numbered list"
          className="btn-ghost"
          active={hasAncestorOfType(schema.nodes.ordered_list)}
          onMouseDown={() =>
            runCmd(toggleList(schema.nodes.ordered_list as NodeType, schema.nodes.regular_list_item as NodeType))
          }
        />
      )}
      {shows("taskList") && (
        <ToolButton
          icon="check_box"
          title="Task list"
          className="btn-ghost"
          active={hasAncestorOfType(schema.nodes.task_list_item)}
          onMouseDown={() => runCmd(toggleTaskList)}
        />
      )}
      {shows("link") && (
        <div ref={linkAnchorRef} className="relative">
          <ToolButton
            icon="link"
            title="Link"
            className="btn-ghost"
            active={linkDialogOpen}
            disabled={
              !isMarkActive(schema.marks.link) &&
              actions.lastSelectionRef.current.from === actions.lastSelectionRef.current.to
            }
            onMouseDown={openLinkDialog}
          />
          {linkDialogOpen && (
            <LinkDialog
              anchorRef={linkAnchorRef}
              defaultUrl={linkDefaultUrl}
              onApply={handleApplyLink}
              onCancel={() => setLinkDialogOpen(false)}
            />
          )}
        </div>
      )}
      {shows("image") && attachments && (
        <ToolButton icon="attach_file" title="Attach file" className="btn-ghost" onMouseDown={triggerAttach} />
      )}
      {hasKlipy && klipyApiKey && (
        <div className="relative">
          <GifPicker klipyApiKey={klipyApiKey} onSelectGif={handleSelectGif} buttonClassName="btn-ghost" />
        </div>
      )}
      {(enableTableInsert || inTable) && (
        <div ref={tableWrapperRef} className="relative">
          <ToolButton
            icon="table"
            title={inTable ? "Table options" : "Insert table"}
            className="btn-ghost"
            active={tableDialog.open || inTable}
            onMouseDown={() =>
              setTableDialog(prev => (prev.open ? { ...prev, open: false } : { open: true, inTable }))
            }
          />
          {tableDialog.open && (
            <TableDialog
              inTable={tableDialog.inTable}
              onClose={() => setTableDialog(prev => ({ ...prev, open: false }))}
            />
          )}
        </div>
      )}
      {onToggleZen && (
        <ToolButton icon="open_in_full" title="Zen mode" className="btn-ghost" onMouseDown={onToggleZen} />
      )}
    </div>
  )
}
