import { useEffect, useRef } from "react"

import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { useWorkspaceVisitRecording } from "~/react/shared/hooks/useVisitRecording"
import { ErrorState } from "~/react/ui/ErrorState"
import { CompletedView } from "./CompletedView"
import { useBotStateChannel } from "./hooks/useBotStateChannel"
import { useMeetingShow } from "./hooks/useMeetingShow"
import { MeetingShowSkeleton } from "./MeetingShowSkeleton"
import type { MeetingShowProps } from "./types"
import { UpcomingView } from "./UpcomingView"

// A single island for every lifecycle state of a meeting. It loads the meeting
// + bot once, then branches: an upcoming meeting gets the agenda / recording
// view, everything else gets the completed recording / transcript view. The
// shared header, sharing, collection, and title editing live in components used
// by both views.
export function MeetingShow({ meetingId, back }: MeetingShowProps) {
  const { meeting, bot, loading, error, applyLocalUpdate, applyServerUpdate, applyBotUpdate, refetch } =
    useMeetingShow(meetingId)

  // Subscribe only when a bot exists, mirroring the prior topic-gated behavior.
  useBotStateChannel(bot ? meetingId : null, applyBotUpdate)

  // Boost the back link (and recurring prev/next meeting links) so navigating is
  // a same-realm navigation, not a hard reload that strands a detached realm
  // until GC (#8744). The wrapper below encloses whichever view renders, so one
  // process covers both the upcoming and completed branches. Key the dep on the
  // loaded gate so htmx.process runs in the render that mounts the wrapper.
  const rootRef = useRef<HTMLDivElement>(null)
  useBoostIslandLinks(rootRef, [!loading && !!meeting])

  // Record the workspace visit once, after the meeting loads — matching how
  // postShow / emailThreadShow record. Recording on page load would bump
  // last_visit_at to "now" before this fetch resolves, so "what's new" would
  // never render. No last_event_id, reproducing the prior beacon's behavior.
  const recordVisit = useWorkspaceVisitRecording(meeting?.workspace_id ?? null)
  const trackedVisitRef = useRef(false)
  useEffect(() => {
    if (!meeting || trackedVisitRef.current) return
    trackedVisitRef.current = true
    recordVisit()
  }, [meeting, recordVisit])

  if (error) {
    return <ErrorState message="Failed to load this meeting. Please try refreshing the page." />
  }

  if (loading || !meeting) {
    return <MeetingShowSkeleton />
  }

  return (
    <div ref={rootRef}>
      {meeting.is_upcoming ? (
        <UpcomingView
          meeting={meeting}
          bot={bot}
          back={back}
          onLocalUpdate={applyLocalUpdate}
          onServerUpdate={applyServerUpdate}
          onBotUpdate={applyBotUpdate}
        />
      ) : (
        <CompletedView
          meeting={meeting}
          bot={bot}
          back={back}
          onLocalUpdate={applyLocalUpdate}
          onServerUpdate={applyServerUpdate}
          refetch={refetch}
        />
      )}
    </div>
  )
}
