import { useCallback, useEffect, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { Goal } from "~/react/shared/types"
import { FLOATING_PORTAL_ROOT_ID } from "~/react/ui/floatingPortalRoot"
import { showFlash } from "~/shared/flash"

import { useTimelineComposer } from "../hooks/useTimelineComposer"
import type { GoalUpdateSubmitData } from "../types"
import { UpdateForm } from "./UpdateForm"

interface TimelineComposerProps {
  goal: Goal
  currentUserId: string
  onSubmitted?: () => void
  onGoalUpdated?: (goal: Goal) => void
  noAutoScroll?: boolean
}

export function TimelineComposer({
  goal,
  currentUserId,
  onSubmitted,
  onGoalUpdated,
  noAutoScroll,
}: TimelineComposerProps) {
  const isOwner = goal.owner?.id === currentUserId
  const canCompose = isOwner && !goal.is_closed && !goal.is_draft

  if (canCompose) {
    return (
      <TimelineUpdateComposer
        goal={goal}
        onSubmitted={onSubmitted}
        onGoalUpdated={onGoalUpdated}
        noAutoScroll={noAutoScroll}
      />
    )
  }

  // Non-owners request updates from the header (see RequestUpdateMenu in GoalShow).
  return null
}

function TimelineUpdateComposer({
  goal,
  onSubmitted,
  onGoalUpdated,
  noAutoScroll,
}: {
  goal: Goal
  onSubmitted?: () => void
  onGoalUpdated?: (goal: Goal) => void
  noAutoScroll?: boolean
}) {
  const { questionText, pendingUpdate, submitting, submitUpdate, completeGoal, saveDraft } = useTimelineComposer(goal)
  const [expanded, setExpanded] = useState(false)
  // Keep UpdateForm mounted during the close animation so it slides out rather than snapping away.
  const [keepMounted, setKeepMounted] = useState(false)

  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const composerRef = useRef<HTMLDivElement>(null)
  const hasContentRef = useRef(false)
  const markDirty = useCallback((dirty: boolean) => {
    hasContentRef.current = dirty
  }, [])

  const expand = useCallback(() => {
    clearTimeout(closeTimerRef.current)
    setKeepMounted(true)
    setExpanded(true)
  }, [])

  const collapse = useCallback(() => {
    setExpanded(false)
    clearTimeout(closeTimerRef.current)
    // Unmount form content after the animation finishes (duration-200 + small buffer)
    closeTimerRef.current = setTimeout(() => setKeepMounted(false), 320)
  }, [])

  const refreshGoal = useCallback(async () => {
    try {
      const updated = await apiFetch<Goal>(`/api/goals/${goal.id}`)
      onGoalUpdated?.(updated)
    } catch {
      // Card will show stale data until next navigation — not fatal.
    }
  }, [goal.id, onGoalUpdated])

  const handleSubmit = useCallback(
    async (data: GoalUpdateSubmitData) => {
      try {
        await submitUpdate(data)
      } catch {
        showFlash("Failed to submit update. Please try again.", "error")
        return
      }
      collapse()
      onSubmitted?.()
      void refreshGoal()
    },
    [submitUpdate, onSubmitted, collapse, refreshGoal]
  )

  const handleComplete = useCallback(
    async (data: Omit<GoalUpdateSubmitData, "is_draft">) => {
      try {
        await completeGoal(data)
      } catch {
        showFlash("Failed to complete goal. Please try again.", "error")
        return
      }
      collapse()
      onSubmitted?.()
      void refreshGoal()
    },
    [completeGoal, onSubmitted, collapse, refreshGoal]
  )

  useEffect(() => {
    if (!expanded) return
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node
      if (composerRef.current?.contains(target)) return
      // Dropdown panels render into a FloatingPortal outside the composer's DOM
      // subtree — treat clicks inside the portal as still within the composer.
      if (document.getElementById(FLOATING_PORTAL_ROOT_ID)?.contains(target)) return
      // Never discard an in-progress update on a stray outside click — the
      // user dismisses an unwanted composer explicitly via Cancel.
      if (hasContentRef.current) return
      collapse()
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [expanded, collapse])

  useEffect(() => {
    if (!expanded || noAutoScroll) return
    // Scroll to the composer itself — it sits above the timeline, so scrolling to the page bottom
    // would land well past the form.
    const id = requestAnimationFrame(() => {
      composerRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
    })
    return () => cancelAnimationFrame(id)
  }, [expanded, noAutoScroll])

  useEffect(() => () => clearTimeout(closeTimerRef.current), [])

  return (
    <div ref={composerRef} className="px-4 mt-6 mb-6">
      <div className="bg-base-50 rounded-xl border border-base-300 shadow-xs relative">
        {/* Badge chip — fades in with the form */}
        {expanded && (
          <div className="absolute left-3 -top-3 dropdown-card rounded-lg inline-flex items-center px-2 py-1 shadow-sm">
            <span className="text-xs text-base-600/70 font-semibold">New Update</span>
          </div>
        )}

        {/* Collapsed placeholder — slides up as card opens */}
        <div
          className={`grid transition-[grid-template-rows] duration-300 ease-entrance ${
            expanded ? "grid-rows-[0fr]" : "grid-rows-[1fr]"
          }`}
        >
          <div className="overflow-hidden">
            <button type="button" onClick={expand} className="w-full px-4 py-2.5 text-left cursor-text">
              <span
                className={`text-sm text-base-content/40 transition-opacity duration-150 ${expanded ? "opacity-0" : "opacity-100"}`}
              >
                Share an update…
              </span>
            </button>
          </div>
        </div>

        {/* Expanded form — slides down as card opens */}
        <div
          className={`grid transition-[grid-template-rows] duration-300 ease-entrance ${
            expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
          }`}
        >
          <div className="overflow-hidden">
            {keepMounted && (
              <UpdateForm
                key={goal.id}
                goal={goal}
                questionText={questionText}
                initialAnswer={pendingUpdate?.answer_text ?? undefined}
                onSubmit={handleSubmit}
                onComplete={handleComplete}
                onCancel={collapse}
                submitting={submitting}
                onDraftChange={saveDraft}
                onDirtyChange={markDirty}
                noCard
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
