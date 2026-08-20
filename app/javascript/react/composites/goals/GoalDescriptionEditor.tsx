import { useCallback, useEffect, useRef, useState } from "react"

import type { Goal, GoalSummary } from "~/react/shared/types"

import { useGoalFieldSave } from "./useGoalFieldSave"

interface GoalDescriptionEditorProps {
  goal: Goal | GoalSummary
  onGoalUpdated: (goal: Goal) => void
  isSubgoal?: boolean
}

export function GoalDescriptionEditor({ goal, onGoalUpdated, isSubgoal }: GoalDescriptionEditorProps) {
  const [descriptionEditValue, setDescriptionEditValue] = useState<string | null>(null)
  const descriptionIsEditing = descriptionEditValue !== null

  return (
    <>
      <div className={`flex-1 flex flex-col gap-2 min-w-0 ${isSubgoal ? "p-4" : "py-5 pl-2 pr-4"}`}>
        <TitleEditor goal={goal} onGoalUpdated={onGoalUpdated} />
        <DescriptionEditor
          goal={goal}
          onGoalUpdated={onGoalUpdated}
          isSubgoal={isSubgoal}
          editValue={descriptionEditValue}
          setEditValue={setDescriptionEditValue}
        />
      </div>
      {!goal.is_draft && !descriptionIsEditing && (
        <button
          type="button"
          onClick={e => {
            e.stopPropagation()
            setDescriptionEditValue(goal.description)
          }}
          className="shrink-0 p-1 mr-2 text-base-content/40 hover:text-base-content/60 transition-opacity [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
        >
          <span className="material-symbols-outlined text-base">edit</span>
        </button>
      )}
    </>
  )
}

function TitleEditor({ goal, onGoalUpdated }: GoalDescriptionEditorProps) {
  const [editValue, setEditValue] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const saveField = useGoalFieldSave(goal, onGoalUpdated)
  const isEditing = editValue !== null

  useEffect(() => {
    if (isEditing) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [isEditing])

  function startEditing() {
    setEditValue(goal.title ?? "")
  }

  const save = useCallback(async () => {
    if (editValue === null) return
    const trimmed = editValue.trim()
    setEditValue(null)
    if (!trimmed || trimmed === (goal.title ?? "")) return
    await saveField("title", trimmed)
  }, [editValue, goal.title, saveField])

  function cancel() {
    setEditValue(null)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault()
      save()
    } else if (e.key === "Escape") {
      e.preventDefault()
      cancel()
    }
  }

  return (
    <div
      className={`inline-flex items-center gap-2 group/title w-fit px-2.5 py-0 -mx-2.5 -my-1 min-h-6 rounded-md transition-shadow cursor-default ${
        isEditing ? "ring-1 ring-base-content/30" : "hover:ring-1 hover:ring-base-content/20"
      }`}
      onClick={e => {
        if (!isEditing) {
          e.stopPropagation()
          startEditing()
        }
      }}
    >
      {isEditing ? (
        <input
          ref={inputRef}
          type="text"
          value={editValue}
          onChange={e => setEditValue(e.target.value)}
          onBlur={save}
          onKeyDown={handleKeyDown}
          className="text-xs font-medium text-base-content/50 leading-none outline-none bg-transparent cursor-text w-full"
        />
      ) : (
        <>
          <span className="text-xs font-medium text-base-content/50 leading-none truncate">{goal.title || ""}</span>
          <button
            type="button"
            onClick={e => {
              e.stopPropagation()
              startEditing()
            }}
            className="shrink-0 text-base-content/30 hover:text-base-content/60 opacity-0 group-hover/title:opacity-100 transition-opacity"
          >
            <span className="material-symbols-outlined text-sm">edit</span>
          </button>
        </>
      )}
    </div>
  )
}

interface DescriptionEditorInternalProps extends GoalDescriptionEditorProps {
  editValue: string | null
  setEditValue: (value: string | null) => void
}

function DescriptionEditor({
  goal,
  onGoalUpdated,
  isSubgoal,
  editValue,
  setEditValue,
}: DescriptionEditorInternalProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const saveField = useGoalFieldSave(goal, onGoalUpdated)
  const isEditing = editValue !== null

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      const el = textareaRef.current
      el.focus()
      el.select()
      // Auto-size to content
      el.style.height = "auto"
      el.style.height = `${el.scrollHeight}px`
    }
  }, [isEditing])

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  const saveValue = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || trimmed === goal.description) return
      await saveField("description", trimmed)
    },
    [goal.description, saveField]
  )

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const newValue = e.target.value
    setEditValue(newValue)

    // Auto-size textarea to content
    const el = e.target
    el.style.height = "auto"
    el.style.height = `${el.scrollHeight}px`

    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => saveValue(newValue), 1000)
  }

  function handleBlur() {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (editValue !== null) saveValue(editValue)
    setEditValue(null)
  }

  function cancel() {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    setEditValue(null)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (debounceRef.current) clearTimeout(debounceRef.current)
      if (editValue !== null) saveValue(editValue)
      setEditValue(null)
    } else if (e.key === "Escape") {
      e.preventDefault()
      cancel()
    }
  }

  if (isEditing) {
    return (
      <textarea
        ref={textareaRef}
        value={editValue}
        onChange={handleChange}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        rows={1}
        className={`outline-none text-sm bg-transparent cursor-text w-full resize-none overflow-hidden ${isSubgoal ? "text-base-content/90" : "text-base-content font-semibold"}`}
      />
    )
  }

  return (
    <span
      className={`text-sm cursor-default ${isSubgoal ? "text-base-content/90" : "text-base-content font-semibold"}`}
      onClick={e => {
        e.stopPropagation()
        setEditValue(goal.description)
      }}
    >
      {goal.description}
    </span>
  )
}
