import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core"
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import type { GoalsView } from "~/react/features/goalsIndex/types"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import type { Goal } from "~/react/shared/types"
import { EmptyState } from "~/react/ui/EmptyState"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadMoreSentinel } from "~/react/ui/LoadMoreSentinel"
import { ActivateDialog } from "./components/ActivateDialog"
import { GoalCreationRow } from "./components/GoalCreationRow"
import { GoalEditRow } from "./components/GoalEditRow"
import { GoalIndexRow } from "./components/GoalIndexRow"
import { GoalsFirstRun } from "./components/GoalsFirstRun"
import { GoalsHeader } from "./components/GoalsHeader"
import { GoalsListSkeleton } from "./GoalsListSkeleton"
import { useGoalsChannel } from "./hooks/useGoalsChannel"
import { useGoalsData } from "./hooks/useGoalsData"

function GoalsEmptyState({
  view,
  isFiltered,
  onClearFilters,
  onStartCreating,
}: {
  view: GoalsView
  isFiltered: boolean
  onClearFilters: () => void
  onStartCreating: () => void
}) {
  if (isFiltered) {
    return (
      <EmptyState title="No matching goals" text="Try adjusting your filters to see more goals.">
        <button onClick={onClearFilters} className="btn btn-sm btn-ghost">
          Clear filters
        </button>
      </EmptyState>
    )
  }

  if (view === "completed") {
    return (
      <EmptyState
        title="No completed goals"
        text="Track your progress and celebrate your achievements by completing goals."
      />
    )
  }

  if (view === "closed") {
    return (
      <EmptyState title="No closed goals" text="Closed goals that are no longer being pursued will appear here." />
    )
  }

  return <GoalsFirstRun onStartCreating={onStartCreating} />
}

export function GoalsIndex() {
  const {
    goals,
    loading,
    loadingMore,
    error,
    hasMore,
    loadMore,
    view,
    changeView,
    ownerIds,
    groupIds,
    toggleOwnerFilter,
    toggleGroupFilter,
    clearFilters,
    isFiltered,
    isPlanningList,
    planningListNames,
    updateGoalInList,
    removeGoal,
    addGoalToList,
    reorderGoals,
    reorderSubgoals,
    isSortEnabled,
  } = useGoalsData()

  const { presentUsers } = useGoalsChannel(view)
  const { users: organizationUsers, groups: organizationGroups } = useOrganizationMembers()

  const [isCreating, setIsCreating] = useState(false)
  const [showActivateDialog, setShowActivateDialog] = useState(false)
  const [highlightedGoalId, setHighlightedGoalId] = useState<string | null>(null)
  const [openCommentsGoalId, setOpenCommentsGoalId] = useState<string | null>(null)
  // `#goal-{id}` deep links come from the Goal/GoalComment gid redirects
  // (global_ids.py), which are full-document loads into the shell — so the hash is
  // on window.location at mount and no client navigation can change it while this
  // page is up. Reading it directly is therefore equivalent to useLocation().hash.
  const initialHash = window.location.hash
  const targetGoalIdRef = useRef<string | null>(
    initialHash.startsWith("#goal-") ? initialHash.slice("#goal-".length) : null
  )
  // Hash fragment deep-link: scroll to and highlight the target goal, loading
  // more pages as needed until it's found.
  useEffect(() => {
    const targetId = targetGoalIdRef.current
    if (!targetId || loading) return

    const found = goals.some(g => g.id === targetId || (g.subgoals ?? []).some(s => s.id === targetId))
    if (found) {
      targetGoalIdRef.current = null
      setHighlightedGoalId(targetId)
      requestAnimationFrame(() => {
        document.getElementById(`goal-${targetId}`)?.scrollIntoView({ behavior: "smooth", block: "center" })
      })
      return
    }

    if (hasMore && !loadingMore) {
      loadMore()
    } else if (!hasMore) {
      targetGoalIdRef.current = null
    }
  }, [goals, loading, loadingMore, hasMore, loadMore])

  // Clear highlight when CSS animation ends — separated so channel broadcasts don't cancel it
  useEffect(() => {
    if (!highlightedGoalId) return
    const el = document.getElementById(`goal-${highlightedGoalId}`)?.firstElementChild
    if (!el) return
    const onEnd = () => setHighlightedGoalId(null)
    el.addEventListener("animationend", onEnd, { once: true })
    const fallback = setTimeout(onEnd, 4000)
    return () => {
      el.removeEventListener("animationend", onEnd)
      clearTimeout(fallback)
    }
  }, [highlightedGoalId])

  const startCreating = useCallback(() => {
    setIsCreating(true)
  }, [])

  const handleGoalCreated = useCallback(
    (goal: Goal) => {
      addGoalToList(goal)
      if (!isPlanningList) {
        setIsCreating(false)
      }
    },
    [addGoalToList, isPlanningList]
  )

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return

    const oldIndex = goals.findIndex(g => g.id === String(active.id))
    const newIndex = goals.findIndex(g => g.id === String(over.id))
    if (oldIndex === -1 || newIndex === -1) return
    reorderGoals(arrayMove(goals, oldIndex, newIndex))
  }

  const goalIds = useMemo(() => goals.map(g => g.id), [goals])

  return (
    <div>
      <GoalsHeader
        view={view}
        onChangeView={changeView}
        planningListNames={planningListNames}
        ownerIds={ownerIds}
        groupIds={groupIds}
        onToggleOwner={toggleOwnerFilter}
        onToggleGroup={toggleGroupFilter}
        onClearFilters={clearFilters}
        orgUsers={organizationUsers}
        orgGroups={organizationGroups}
        isPlanningList={isPlanningList}
        onStartCreating={startCreating}
        onActivate={() => setShowActivateDialog(true)}
        goalsCount={goals.length}
        presentUsers={presentUsers}
      />
      <div className="w-full px-[9px]">
        {loading && goals.length === 0 ? (
          <GoalsListSkeleton />
        ) : error ? (
          <div className="border-b border-base-300">
            <ErrorState message="Failed to load goals. Please try refreshing the page." />
          </div>
        ) : (
          <>
            {isCreating && !isPlanningList && (
              <GoalCreationRow
                isClosable={goals.length > 0}
                onCreated={handleGoalCreated}
                onCancel={() => setIsCreating(false)}
              />
            )}
            {goals.length === 0 && !isCreating && !isPlanningList ? (
              <GoalsEmptyState
                view={view}
                isFiltered={isFiltered}
                onClearFilters={clearFilters}
                onStartCreating={startCreating}
              />
            ) : (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={goalIds} strategy={verticalListSortingStrategy}>
                  <ol>
                    {goals.map(goal =>
                      isPlanningList ? (
                        <GoalEditRow
                          key={goal.id}
                          goal={goal}
                          isPlanningList
                          isSortEnabled={isSortEnabled}
                          isHighlighted={highlightedGoalId === goal.id}
                          defaultExpanded
                          organizationUsers={organizationUsers}
                          organizationGroups={organizationGroups}
                          onGoalUpdated={updateGoalInList}
                          onGoalRemoved={removeGoal}
                          onReorderSubgoals={reorderSubgoals}
                          openCommentsGoalId={openCommentsGoalId}
                          onToggleComments={setOpenCommentsGoalId}
                        />
                      ) : (
                        <GoalIndexRow
                          key={goal.id}
                          goal={goal}
                          isSortEnabled={isSortEnabled}
                          isHighlighted={highlightedGoalId === goal.id}
                          organizationUsers={organizationUsers}
                          organizationGroups={organizationGroups}
                          onGoalUpdated={updateGoalInList}
                          onGoalRemoved={removeGoal}
                          onReorderSubgoals={reorderSubgoals}
                          openCommentsGoalId={openCommentsGoalId}
                          onToggleComments={setOpenCommentsGoalId}
                        />
                      )
                    )}
                  </ol>
                </SortableContext>
              </DndContext>
            )}
            {isPlanningList && (
              <GoalCreationRow planningListName={view} isClosable={false} onCreated={handleGoalCreated} />
            )}
          </>
        )}
        {hasMore && <LoadMoreSentinel onIntersect={loadMore} loading={loadingMore} />}
      </div>
      {showActivateDialog && (
        <ActivateDialog
          planningListName={view}
          onActivated={() => {
            setShowActivateDialog(false)
            changeView("active")
          }}
          onClose={() => setShowActivateDialog(false)}
        />
      )}
    </div>
  )
}
