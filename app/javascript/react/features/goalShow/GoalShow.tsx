import { getRouteApi } from "@tanstack/react-router"

import { BackButton } from "~/react/composites/BackButton"
import { GoalActionsMenu } from "~/react/composites/goals/GoalActionsMenu"
import { GroupPicker } from "~/react/composites/GroupPicker"
import { MailboxActionBar, mailboxActionUrls } from "~/react/composites/MailboxActionBar"
import { OwnerPicker } from "~/react/composites/OwnerPicker"
import { StatusDropdown } from "~/react/composites/StatusDropdown"
import { TargetDatePicker } from "~/react/composites/TargetDatePicker"
import { backNavigation } from "~/react/shared/backNavigation"
import { boostedNavigate } from "~/react/shared/boostedNavigate"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import { useWorkspaceViewState } from "~/react/shared/hooks/useWorkspaceViewState"
import type { Goal } from "~/react/shared/types"
import { ErrorState } from "~/react/ui/ErrorState"
import { StickyHeader } from "~/react/ui/StickyHeader"

import { EditableGoalDescription, EditableGoalTitle } from "./components/GoalHeadingEditors"
import { GoalTimeline } from "./components/GoalTimeline"
import { RequestUpdateMenu } from "./components/RequestUpdateMenu"
import { TimelineComposer } from "./components/TimelineComposer"
import { GoalShowSkeleton } from "./GoalShowSkeleton"
import { useGoalShowState } from "./hooks/useGoalShowState"
import { useGoalTimeline } from "./hooks/useGoalTimeline"
import { useVisibleVisitRecording } from "./hooks/useVisibleVisitRecording"
import type { TimelineEvent } from "./types"

// The route id carries the pathless shell parent prefix (shellRoute has id
// "shell"), so the typed accessor is addressed as "/shell/goals/$goalId".
const routeApi = getRouteApi("/shell/goals/$goalId")

export function GoalShow() {
  const { goalId } = routeApi.useParams()
  const { return_to: returnTo, mailbox_entry_id: mailboxEntryId } = routeApi.useSearch()
  const { goal, mailboxEntry, setMailboxEntry, loading, error, handleGoalUpdated, refetchGoal } = useGoalShowState(
    goalId,
    mailboxEntryId
  )
  // Read here rather than inside GoalShowContent so the skeleton covers both
  // fetches, as the old Promise.all did — otherwise the header paints above an
  // empty timeline.
  const { events, loading: timelineLoading, error: timelineError } = useGoalTimeline(goalId)
  const { user, error: userError } = useCurrentUser()
  const { users: orgUsers, groups: orgGroups } = useOrganizationMembers()

  useDocumentTitle(goal?.title || goal?.description || "Goal")

  // Replicates the old server-side back_navigation(fallback_route="goals_index"),
  // which no longer runs — the API request doesn't carry the page URL's return_to.
  // The inbox is the fallback when the goal was opened from a mailbox entry (that
  // href carries mailbox_entry_id and no return_to), else the goals index.
  const back = backNavigation(
    returnTo,
    mailboxEntryId ? { url: "/", label: "Back to inbox" } : { url: "/goals", label: "Back to goals" }
  )

  if (error || timelineError || userError) {
    return <ErrorState message="Failed to load goal. Please try refreshing the page." />
  }

  if (loading || timelineLoading || !goal || !user) {
    return <GoalShowSkeleton />
  }

  const goBack = () => {
    boostedNavigate(back.url)
  }

  // Non-owners get a header-anchored "Request update" affordance instead of a content-area form,
  // so the goal's status stays the primary thing on the page.
  const canRequest = !!goal.owner && goal.owner.id !== user.id && !goal.is_closed && !goal.is_draft

  const headerActions = (
    <div className="flex items-center gap-2">
      {canRequest && goal.owner && <RequestUpdateMenu goalId={goal.id} ownerName={goal.owner.display_name} />}
      <GoalActionsMenu
        goal={goal}
        onClose={goBack}
        onReactivate={refetchGoal}
        onDelete={goBack}
        trigger={
          <button type="button" className="btn border border-neutral font-normal text-base-600">
            <span className="material-symbols-outlined text-[16px]">more_horiz</span>
          </button>
        }
      />
    </div>
  )

  return (
    <div>
      <StickyHeader>
        <div className="flex items-center justify-between gap-2 p-2">
          {mailboxEntry ? (
            <MailboxActionBar
              state={{
                isUnread: mailboxEntry.is_unread,
                isArchived: mailboxEntry.is_archived,
                isSnoozed: mailboxEntry.is_snoozed,
                snoozedUntil: mailboxEntry.snoozed_until,
              }}
              actionUrls={mailboxActionUrls(mailboxEntry.id)}
              back={back}
              navLink
              trailingSlot={headerActions}
              onStateChange={next =>
                setMailboxEntry({
                  id: mailboxEntry.id,
                  is_unread: next.isUnread,
                  is_archived: next.isArchived,
                  is_snoozed: next.isSnoozed,
                  snoozed_until: next.snoozedUntil,
                })
              }
            />
          ) : (
            <>
              <BackButton
                back={back}
                navLink
                className="border border-neutral font-normal text-base-600 flex items-center gap-1"
              />
              {headerActions}
            </>
          )}
        </div>
      </StickyHeader>

      <div className="max-w-3xl mx-auto">
        {/* Title + description sit naked on the background, above everything else. The title is a
            short label; the description is the goal itself, so it's the prominent line. Both are
            editable inline, alongside the owner and due date. */}
        {/* One flex-wrap container so the order can differ by breakpoint via `order`:
            - sm+: title (left) and pickers (right) share row 1; description fills row 2.
            - mobile: title, then description, then the pickers — pickers drop below both. */}
        <div className="px-4 mb-4 flex flex-wrap items-center gap-y-2 sm:gap-x-4">
          <div className="order-1 basis-full sm:basis-auto">
            <EditableGoalTitle goal={goal} onGoalUpdated={handleGoalUpdated} />
          </div>
          {/* Two sub-groups so mobile gets two rows (status+date, then owner+group) while sm+
              keeps a single owner, group, status, date row. */}
          <div className="order-3 basis-full flex flex-wrap items-center gap-x-4 gap-y-2 sm:order-2 sm:basis-auto sm:ml-auto">
            <div className="order-1 basis-full flex items-center gap-x-4 sm:order-2 sm:basis-auto">
              <StatusDropdown goal={goal} onGoalUpdated={handleGoalUpdated} />
              {!goal.is_completed && (
                <span className="flex items-center gap-1 text-base-content/60">
                  <span className="material-symbols-outlined text-[16px]">calendar_today</span>
                  <TargetDatePicker goal={goal} onGoalUpdated={handleGoalUpdated} />
                </span>
              )}
            </div>
            <div className="order-2 basis-full flex items-center gap-x-4 sm:order-1 sm:basis-auto">
              <OwnerPicker goal={goal} users={orgUsers} onGoalUpdated={handleGoalUpdated} />
              <GroupPicker goal={goal} groups={orgGroups} onGoalUpdated={handleGoalUpdated} />
            </div>
          </div>
          <div className="order-2 basis-full sm:order-3">
            <EditableGoalDescription goal={goal} onGoalUpdated={handleGoalUpdated} />
          </div>
        </div>
        {/* No onSubmitted: posting an update records a GOAL_UPDATE_POSTED event, so
            the goal_timeline broadcast carries the new timeline back to this tab. */}
        <TimelineComposer goal={goal} currentUserId={user.id} onGoalUpdated={handleGoalUpdated} noAutoScroll />
        <GoalShowContent key={goal.id} goal={goal} events={events} currentUserId={user.id} />
      </div>
    </div>
  )
}

function GoalShowContent({
  goal,
  events,
  currentUserId,
}: {
  goal: Goal
  events: TimelineEvent[]
  currentUserId: string
}) {
  const { lastSeenEventId, readersByEventId, ready } = useWorkspaceViewState(goal.workspace_id, currentUserId)
  const newestEventId = events.length > 0 ? events[events.length - 1].id : null
  useVisibleVisitRecording(goal.workspace_id, newestEventId, ready)

  return (
    <div>
      {/* The latest update is just the newest timeline entry — keeping it inline (rather than
          hoisting it into a separate card) keeps every event in chronological order, so a later
          status change can't appear to sit below a newer update. */}
      <GoalTimeline events={events} lastSeenEventId={lastSeenEventId} readersByEventId={readersByEventId} />
    </div>
  )
}
