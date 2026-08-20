import { useCallback, useEffect, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { Goal } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"
import type { GoalUpdateSubmitData } from "../types"

interface PendingUpdate {
  id: string | null
  question_text: string
  status: string | null
  progress: number | null
  answer_text: string | null
}

// The draft payload captured at type-time. goalId and updateId are snapshotted here rather than
// read from a cleanup effect closure: the [goal.id] effect does not re-run when pendingUpdate
// resolves, so its closure would hold a stale (usually null) update id and target the wrong row.
interface PendingDraft {
  goalId: string
  updateId: string | null
  data: GoalUpdateSubmitData
}

interface UseTimelineComposerResult {
  questionText: string
  pendingUpdate: PendingUpdate | null
  submitting: boolean
  submitUpdate: (data: GoalUpdateSubmitData) => Promise<void>
  completeGoal: (data: Omit<GoalUpdateSubmitData, "is_draft">) => Promise<void>
  saveDraft: (data: GoalUpdateSubmitData) => void
}

function postDraft(pending: PendingDraft) {
  // update_id lets the server 204-no-op when the targeted row is no longer pending (a completing
  // submit already resolved it), rather than resurrecting it as a fresh pending update.
  apiFetch(`/api/goals/${pending.goalId}/updates`, {
    method: "POST",
    body: JSON.stringify({ ...pending.data, is_draft: true, update_id: pending.updateId }),
  }).catch(() => {
    // Draft save is best-effort.
  })
}

export function useTimelineComposer(goal: Goal): UseTimelineComposerResult {
  const [questionText, setQuestionText] = useState("How's it going?")
  const [pendingUpdate, setPendingUpdate] = useState<PendingUpdate | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const draftTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const latestDraftRef = useRef<PendingDraft | null>(null)
  const cancelledRef = useRef(false)

  // Reset stale data immediately when the goal changes so the composer never shows
  // the previous goal's question or answer while the new fetch is in-flight.
  const [observedGoalId, setObservedGoalId] = useState(goal.id)
  if (observedGoalId !== goal.id) {
    setObservedGoalId(goal.id)
    setQuestionText("How's it going?")
    setPendingUpdate(null)
  }

  useEffect(() => {
    let cancelled = false

    apiFetch<PendingUpdate>(`/api/goals/${goal.id}/updates/pending`).then(
      pending => {
        if (cancelled || !pending) return
        setQuestionText(pending.question_text)
        setPendingUpdate(pending)
        // A loaded draft only pre-fills the composer's content; it never opens the composer.
      },
      () => {
        if (!cancelled) showFlash("Couldn't load your update prompt. A default question is shown instead.", "error")
      }
    )

    return () => {
      cancelled = true
    }
  }, [goal.id])

  // Discard an armed draft without saving. Submit/complete call this first so a submit-triggered
  // navigation leaves no armed timer and no pending draft — the gate that keeps flushDraft from
  // resurrecting the row the submit just completed.
  const cancelDraft = useCallback(() => {
    if (draftTimerRef.current) {
      clearTimeout(draftTimerRef.current)
      draftTimerRef.current = null
    }
    latestDraftRef.current = null
  }, [])

  // Save the last-typed draft immediately, targeting the goal it was typed against. Gated on an
  // armed timer, so it no-ops after a submit/complete (which called cancelDraft) or after the
  // debounce already fired. Nulling the timer + ref makes a second call (e.g. the two cleanups
  // both running on unmount) a no-op, so the draft is never double-posted.
  const flushDraft = useCallback(() => {
    if (!draftTimerRef.current) return
    clearTimeout(draftTimerRef.current)
    draftTimerRef.current = null
    const pending = latestDraftRef.current
    latestDraftRef.current = null
    if (pending) postDraft(pending)
  }, [])

  useEffect(() => {
    return () => {
      cancelledRef.current = true
      flushDraft()
    }
  }, [flushDraft])

  // Flush the pending draft when navigating to another goal. A stepper swap changes goal.id
  // without unmounting the composer, so the last edit to the goal being left would otherwise be
  // silently dropped. flushDraft targets the goal captured in latestDraftRef, not the new one.
  useEffect(() => {
    return () => {
      flushDraft()
    }
  }, [goal.id, flushDraft])

  const saveDraft = useCallback(
    (data: GoalUpdateSubmitData) => {
      latestDraftRef.current = { goalId: goal.id, updateId: pendingUpdate?.id ?? null, data }
      if (draftTimerRef.current) clearTimeout(draftTimerRef.current)
      draftTimerRef.current = setTimeout(() => {
        draftTimerRef.current = null
        if (cancelledRef.current) return
        const pending = latestDraftRef.current
        latestDraftRef.current = null
        if (pending) postDraft(pending)
      }, 2000)
    },
    [goal.id, pendingUpdate?.id]
  )

  const submitUpdate = useCallback(
    async (data: GoalUpdateSubmitData) => {
      cancelDraft()
      setSubmitting(true)
      try {
        await apiFetch(`/api/goals/${goal.id}/updates`, {
          method: "POST",
          body: JSON.stringify(data),
        })
      } finally {
        if (!cancelledRef.current) setSubmitting(false)
      }
    },
    [goal.id, cancelDraft]
  )

  const completeGoal = useCallback(
    async (data: Omit<GoalUpdateSubmitData, "is_draft">) => {
      cancelDraft()
      setSubmitting(true)
      try {
        await apiFetch(`/api/goals/${goal.id}/updates/complete`, {
          method: "POST",
          body: JSON.stringify(data),
        })
      } finally {
        if (!cancelledRef.current) setSubmitting(false)
      }
    },
    [goal.id, cancelDraft]
  )

  return {
    questionText,
    pendingUpdate,
    submitting,
    submitUpdate,
    completeGoal,
    saveDraft,
  }
}
