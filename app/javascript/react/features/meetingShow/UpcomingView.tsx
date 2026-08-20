import type { ReactNode } from "react"

import { useCalendarConnection } from "~/react/shared/hooks/useCalendarConnection"
import type { BackNavigation } from "~/react/shared/types"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { Tooltip } from "~/react/ui/Tooltip"

import { AgendaEditor } from "./components/AgendaEditor"
import { AttendeeList } from "./components/AttendeeList"
import { CalendarMismatchBanner } from "./components/CalendarMismatchBanner"
import { Header } from "./components/Header"
import { MeetingTitle } from "./components/MeetingTitle"
import { RecordingControls } from "./components/RecordingControls"
import type { MeetingBotState, MeetingDetail } from "./types"

interface UpcomingViewProps {
  meeting: MeetingDetail
  bot: MeetingBotState | null
  back: BackNavigation
  onLocalUpdate: <K extends keyof MeetingDetail>(field: K, value: MeetingDetail[K]) => void
  onServerUpdate: (meeting: MeetingDetail) => void
  onBotUpdate: (bot: MeetingBotState) => void
}

export function UpcomingView({ meeting, bot, back, onLocalUpdate, onServerUpdate, onBotUpdate }: UpcomingViewProps) {
  // Microsoft users have no Google calendar/recording backend, so the
  // calendar-mismatch banner and the unsupported-platform recording hint
  // (both Google-specific) must not surface. Default to Google when the
  // connection state is unknown so existing behavior is unchanged.
  const { calendar } = useCalendarConnection()
  const isGoogleAuthenticated = calendar?.is_google_authenticated ?? true

  return (
    <div>
      <StickyHeader>
        <Header meeting={meeting} back={back} onServerUpdate={onServerUpdate} />
      </StickyHeader>
      <div className="px-2 grid gap-6">
        <MeetingTitle meeting={meeting} onLocalUpdate={onLocalUpdate} onServerUpdate={onServerUpdate} />
        {!meeting.is_happening_now && (
          <>
            {/* Gated inside is_happening_now: a "can't be recorded, add it to
                your calendar" banner is pointless once the meeting is live. */}
            {bot && !bot.has_calendar_event && isGoogleAuthenticated && <CalendarMismatchBanner />}
            {bot && (
              <RecordingControls
                meetingId={meeting.id}
                bot={bot}
                isGoogleAuthenticated={isGoogleAuthenticated}
                onBotUpdated={onBotUpdate}
              />
            )}
            <AttendeeList userAttendees={meeting.user_attendees} unresolvedAttendees={meeting.unresolved_attendees} />
          </>
        )}
        {/* Outside the is_happening_now gate so the join link survives once the
            meeting is live — the recording block above unmounts then. */}
        {meeting.conferencing_url && (
          <div className="text-center">
            <a href={meeting.conferencing_url} target="_blank" rel="noopener noreferrer" className="link text-xs">
              Click here to join.
            </a>
          </div>
        )}
        <AgendaTabs>
          <AgendaEditor meetingId={meeting.id} initialContent={meeting.agenda} workspaceId={meeting.workspace_id} />
        </AgendaTabs>
      </div>
    </div>
  )
}

// On an upcoming meeting only Agenda is real; Summary stays disabled with a
// tooltip until the meeting completes (when the completed view's Tabs takes
// over with an editable summary).
function AgendaTabs({ children }: { children: ReactNode }) {
  return (
    <div>
      <div
        role="tablist"
        className="inline-flex items-center gap-0.5 rounded-full border border-base-300 bg-base-200/40 p-0.5"
      >
        <span
          role="tab"
          aria-selected
          className="px-3 py-1 rounded-full text-sm bg-base-100 text-base-content font-medium shadow-xs"
        >
          Agenda
        </span>
        <Tooltip content="The meeting summary will be available after the meeting ends">
          <span
            role="tab"
            aria-disabled="true"
            aria-selected={false}
            className="px-3 py-1 rounded-full text-sm text-base-content/30 flex items-center gap-1 cursor-default"
          >
            Summary <span className="material-symbols-outlined text-base">info</span>
          </span>
        </Tooltip>
      </div>
      <div className="mt-3 rounded-2xl border border-base-300 bg-base-50 group" role="tabpanel">
        {children}
      </div>
    </div>
  )
}
