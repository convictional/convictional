import { useEffect, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { Goal } from "~/react/shared/types"

interface GoalCreationRowProps {
  isSubgoal?: boolean
  parentGoalId?: string
  planningListName?: string | null
  isClosable?: boolean
  // Optional: subgoal creation omits it and relies on the GOALS_INDEX broadcast instead.
  onCreated?: (goal: Goal) => void
  onCancel?: () => void
}

export function GoalCreationRow({
  isSubgoal = false,
  parentGoalId,
  planningListName,
  isClosable = true,
  onCreated,
  onCancel,
}: GoalCreationRowProps) {
  const [title, setTitle] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  function resetForm() {
    setTitle("")
  }

  async function submit() {
    const trimmed = title.trim()
    if (!trimmed || submitting) return

    setSubmitting(true)
    try {
      const body: Record<string, unknown> = {
        description: trimmed,
      }

      if (isSubgoal && parentGoalId) {
        body.parent_id = parentGoalId
      }
      if (planningListName) {
        body.planning_list_name = planningListName
      }

      const goal = await apiFetch<Goal>("/api/goals?expand=subgoals", {
        method: "POST",
        body: JSON.stringify(body),
      })

      onCreated?.(goal)
      resetForm()
      requestAnimationFrame(() => textareaRef.current?.focus())
    } catch {
      // No user-facing error — form text is preserved so the user can retry.
      // Matches the silent-fail pattern used by all editing components in this island.
    } finally {
      setSubmitting(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      submit()
    } else if (e.key === "Escape" && isClosable) {
      e.preventDefault()
      onCancel?.()
    }
  }

  function handleTextareaInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setTitle(e.target.value)
    const el = e.target
    el.style.height = "auto"
    el.style.height = el.scrollHeight + "px"
  }

  return (
    <div
      className={`grid grid-cols-[32px_1fr] md:grid-cols-[32px_1fr_180px_160px_48px] hover:bg-base-200/50 group border-b border-base-300 bg-base-200/30 ${isSubgoal ? "ml-10" : ""}`}
    >
      <div className="flex relative">
        {isClosable && (
          <button
            type="button"
            onClick={() => onCancel?.()}
            className="cursor-pointer hover:bg-base-200 px-2 py-3 text-base-content/60 hover:text-base-content transition-colors absolute inset-0 text-left flex items-center"
          >
            <span className="material-symbols-outlined text-base inline-block">close</span>
          </button>
        )}
      </div>
      <div className="flex items-center gap-1 py-5 relative">
        <textarea
          ref={textareaRef}
          value={title}
          onChange={handleTextareaInput}
          onKeyDown={handleKeyDown}
          placeholder={`Enter ${isSubgoal ? "subgoal" : "goal"} title...`}
          rows={1}
          className={`flex-1 w-full bg-transparent outline-none text-sm resize-none ${
            isSubgoal ? "text-base-content/90 pl-4 pr-4" : "text-base-content font-semibold pl-3 pr-4"
          }`}
        />
        {title.length > 0 && (
          <span
            className={`absolute bottom-1 left-0 text-xs text-base-content/40 ${isSubgoal ? "ml-4" : "ml-3"} flex items-center gap-1`}
          >
            <span className="material-symbols-outlined text-sm">keyboard_return</span> Enter to save
          </span>
        )}
      </div>
      <div className="hidden md:block px-4 py-3" />
      <div className="hidden md:block px-4 py-3" />
    </div>
  )
}
