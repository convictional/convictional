import { useCallback, useRef } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { GoalBadge } from "~/react/composites/goals/GoalBadge"
import { apiFetch } from "~/react/shared/apiFetch"
import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { showFlash } from "~/shared/flash"
import { AddAlignmentForm } from "./components/AddAlignmentForm"
import { AlignedContentList } from "./components/AlignedContentList"
import { AlignmentTimelineChart } from "./components/AlignmentTimelineChart"
import { useAlignmentsShowState } from "./hooks/useAlignmentsShowState"
import { useGoalBadge } from "./hooks/useGoalBadge"
import type { GoalAlignment, GoalAlignmentsShowProps } from "./types"

export function GoalAlignmentsShow({ goalId }: GoalAlignmentsShowProps) {
  const goal = useGoalBadge(goalId)
  const { data, loading, error, refresh, setPinnedLocally } = useAlignmentsShowState(goalId)

  const handleTogglePin = useCallback(
    async (alignment: GoalAlignment) => {
      const next = !alignment.pinned
      // Pinning doesn't change the timeline buckets, so flip locally for an
      // instant response and revert if the request fails.
      setPinnedLocally(alignment.id, next)
      try {
        await apiFetch(`/api/goals/${goalId}/alignments/${alignment.id}`, {
          method: "PATCH",
          body: JSON.stringify({ pinned: next }),
        })
      } catch {
        setPinnedLocally(alignment.id, alignment.pinned)
        showFlash("Couldn't update this alignment. Please try again.", "error")
      }
    },
    [goalId, setPinnedLocally]
  )

  // onDelete is fired from a synchronous onClick, so this Promise is unawaited —
  // it must not reject. Surface failures via a flash rather than an unhandled rejection.
  const handleDelete = useCallback(
    async (alignment: GoalAlignment) => {
      if (!(await confirm({ message: "Remove this alignment?", confirmLabel: "Remove" }))) return
      try {
        await apiFetch(`/api/goals/${goalId}/alignments/${alignment.id}`, { method: "DELETE" })
      } catch {
        showFlash("Couldn't remove this alignment. Please try again.", "error")
        return
      }
      // Deleting removes activity from the timeline, so refetch to reconcile the
      // chart. Best-effort: the delete already committed, so a refresh failure
      // just leaves the list stale until the next load — don't surface it as an
      // error, which would wrongly imply the deletion failed.
      await refresh()
    },
    [goalId, refresh]
  )

  const handleAdd = useCallback(
    async (contentId: string, description: string) => {
      await apiFetch(`/api/goals/${goalId}/alignments`, {
        method: "POST",
        body: JSON.stringify({ content_id: contentId, description }),
      })
      // Refresh is best-effort: the alignment was already created, so a refresh
      // failure must not surface as an add error — that would prompt a retry and
      // a spurious 409. The list reconciles on the next load.
      refresh().catch(() => {})
    },
    [goalId, refresh]
  )

  // Boost the aligned-content source_url anchors so opening one is a same-realm
  // navigation instead of a hard reload that strands the realm (#8744). htmx only
  // wires boost handlers for anchors it saw at scan time, so re-process when the
  // alignment list loads. Cross-origin source_urls fall through to a hard nav.
  const rootRef = useRef<HTMLDivElement>(null)
  useBoostIslandLinks(rootRef, [data?.alignments])

  return (
    <div ref={rootRef}>
      {goal && (
        <div className="mb-6">
          <GoalBadge goal={goal} theme="light" />
        </div>
      )}
      {error ? (
        <ErrorState message="Failed to load aligned content. Please try refreshing the page." />
      ) : loading || !data ? (
        <LoadingState />
      ) : (
        <>
          <AlignmentTimelineChart timeline={data.timeline} />
          <h2 className="text-lg font-semibold mb-4">Goal aligned content</h2>
          <AlignedContentList alignments={data.alignments} onTogglePin={handleTogglePin} onDelete={handleDelete} />
          <div className="mt-3">
            <AddAlignmentForm onSubmit={handleAdd} />
          </div>
        </>
      )}
    </div>
  )
}
