import { type ChangeEvent, type KeyboardEvent, useCallback, useEffect, useRef, useState } from "react"

import { useGoalFieldSave } from "~/react/composites/goals/useGoalFieldSave"
import type { Goal } from "~/react/shared/types"
import { InlineEditTitle } from "~/react/ui/InlineEditTitle"

const HEADLINE_CLASS = "font-accent text-xl font-normal text-base-content text-pretty break-words"

interface EditorProps {
  goal: Goal
  onGoalUpdated: (goal: Goal) => void
}

// Short label in the metadata row. Click (or the pencil) opens a single-line inline input.
export function EditableGoalTitle({ goal, onGoalUpdated }: EditorProps) {
  const [editValue, setEditValue] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const saveField = useGoalFieldSave(goal, onGoalUpdated)
  const editing = editValue !== null

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [editing])

  const save = useCallback(async () => {
    if (editValue === null) return
    const trimmed = editValue.trim()
    setEditValue(null)
    // A blank title is meaningless; an unchanged one isn't worth a request.
    if (!trimmed || trimmed === (goal.title ?? "")) return
    await saveField("title", trimmed)
  }, [editValue, goal.title, saveField])

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault()
      save()
    } else if (e.key === "Escape") {
      e.preventDefault()
      setEditValue(null)
    }
  }

  return (
    <InlineEditTitle
      ref={inputRef}
      displayText={goal.title || "Add a title"}
      editValue={editValue ?? ""}
      editing={editing}
      onEditStart={() => setEditValue(goal.title ?? "")}
      onChange={setEditValue}
      onBlur={save}
      onKeyDown={handleKeyDown}
      className={`text-sm font-medium ${goal.title ? "text-base-content/50" : "text-base-content/40"}`}
    />
  )
}

// The prominent headline. Click to edit in an auto-sizing textarea styled exactly like the h1.
export function EditableGoalDescription({ goal, onGoalUpdated }: EditorProps) {
  const [editValue, setEditValue] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const saveField = useGoalFieldSave(goal, onGoalUpdated)
  const editing = editValue !== null

  useEffect(() => {
    const el = textareaRef.current
    if (editing && el) {
      el.focus()
      el.select()
      el.style.height = "auto"
      el.style.height = `${el.scrollHeight}px`
    }
  }, [editing])

  const save = useCallback(async () => {
    if (editValue === null) return
    const trimmed = editValue.trim()
    setEditValue(null)
    // The description may be cleared, so only an unchanged value is skipped.
    if (trimmed === (goal.description ?? "")) return
    await saveField("description", trimmed)
  }, [editValue, goal.description, saveField])

  function handleChange(e: ChangeEvent<HTMLTextAreaElement>) {
    setEditValue(e.target.value)
    const el = e.target
    el.style.height = "auto"
    el.style.height = `${el.scrollHeight}px`
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      save()
    } else if (e.key === "Escape") {
      e.preventDefault()
      setEditValue(null)
    }
  }

  return (
    <div className="group/desc">
      {/* Ring + pencil mirror the title's editable affordance, scaled up for the headline. The
          ring's negative margin keeps the headline text aligned with the title above it. */}
      <div
        className={`flex items-start gap-2 -ml-3 px-3 py-1.5 rounded-md ring-1 transition-shadow ${
          editing ? "ring-base-300" : "ring-transparent group-hover/desc:ring-base-300"
        }`}
      >
        <div className="flex-1 min-w-0">
          {editing ? (
            <textarea
              ref={textareaRef}
              value={editValue}
              onChange={handleChange}
              onBlur={save}
              onKeyDown={handleKeyDown}
              rows={1}
              className={`${HEADLINE_CLASS} w-full resize-none overflow-hidden bg-transparent outline-none`}
            />
          ) : (
            <h1
              className={`${HEADLINE_CLASS} cursor-text ${goal.description ? "" : "text-base-content/40"}`}
              onClick={() => setEditValue(goal.description ?? "")}
            >
              {goal.description || "Add a description"}
            </h1>
          )}
        </div>
        {/* Pure pointer affordance duplicating the click-to-edit headline — hidden from AT and the
            tab order so it isn't surfaced as a redundant control. */}
        <button
          type="button"
          onClick={editing ? undefined : () => setEditValue(goal.description ?? "")}
          tabIndex={-1}
          aria-hidden="true"
          className={`mt-1 shrink-0 transition-opacity text-base-content/30 hover:text-base-content/60 ${
            editing ? "invisible" : "opacity-0 group-hover/desc:opacity-100 hover:opacity-100"
          }`}
        >
          <span className="material-symbols-outlined text-base">edit</span>
        </button>
      </div>
    </div>
  )
}
