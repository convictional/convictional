import { formatDateTime } from "~/react/ui/DateTime"

import type { MeetingDetail } from "../types"

import { TitleEditor } from "./TitleEditor"

interface MeetingTitleProps {
  meeting: MeetingDetail
  onLocalUpdate: <K extends keyof MeetingDetail>(field: K, value: MeetingDetail[K]) => void
  onServerUpdate: (meeting: MeetingDetail) => void
}

// The meeting heading — title, schedule, and recurring nav — rendered in the
// content area below the sticky header actions, matching the other show pages.
export function MeetingTitle({ meeting, onLocalUpdate, onServerUpdate }: MeetingTitleProps) {
  const scheduledLabel = meeting.scheduled_at
    ? formatDateTime(meeting.scheduled_at, "short_month_day_year_time")
    : "Meeting not scheduled"

  return (
    <div>
      {meeting.is_deleted && <span className="text-lg text-base-500 mb-6">Deleted</span>}
      <TitleEditor
        meetingId={meeting.id}
        title={meeting.title}
        onLocalUpdate={value => onLocalUpdate("title", value)}
        onServerUpdate={onServerUpdate}
      />
      <div className="flex items-center gap-3 mt-1">
        <p className="text-sm text-base-500">{scheduledLabel}</p>
      </div>
      {/* On an upcoming meeting next_meeting only resolves to an already-started
          occurrence, so this link is effectively only shown on completed ones. */}
      {meeting.is_recurring && meeting.next_meeting_id && (
        <div className="flex gap-2 mt-2">
          <div className="tooltip tooltip-right" data-tip="This is a recurring meeting">
            <span className="material-symbols-outlined !text-sm ml-1">event_repeat</span>
          </div>
          <a href={`/meetings/${meeting.next_meeting_id}`} className="link text-sm opacity-75">
            Next meeting
            {meeting.next_meeting_scheduled_at && ` - ${formatDateTime(meeting.next_meeting_scheduled_at, "date")}`}
          </a>
        </div>
      )}
    </div>
  )
}
