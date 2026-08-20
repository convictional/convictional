import type { MeetingResponse } from "~/react/shared/types"
import { DateTime } from "~/react/ui/DateTime"
import { Tooltip } from "~/react/ui/Tooltip"
import { CollectionPicker } from "./CollectionPicker"
import { MeetingAttendees } from "./MeetingAttendees"

interface MeetingCardProps {
  meeting: MeetingResponse
  onMeetingUpdated: (updated: MeetingResponse) => void
  timezone?: string | null
}

// Summary row for the past-meeting list.
export function MeetingCard({ meeting, onMeetingUpdated, timezone }: MeetingCardProps) {
  return (
    <div className="bg-base-50 hover:bg-base-200 transition-colors w-full group" id={`summary_${meeting.id}`}>
      <div className="px-4 py-3">
        <div className="flex flex-col md:flex-row gap-2 md:items-center md:justify-between">
          <div className="flex-1 flex flex-col min-w-0 gap-2 md:gap-0">
            <a href={meeting.source_url} className="group-hover:underline text-sm block truncate">
              <span className="text-sm font-semibold">{meeting.title || "Untitled meeting"}</span>
            </a>
            <p className="text-xs opacity-70 flex items-center gap-1">
              {meeting.scheduled_at && (
                <DateTime datetime={meeting.scheduled_at} format="datetime_long" timezone={timezone} />
              )}
              {meeting.is_recurring && (
                <Tooltip content="This is a recurring meeting">
                  <span className="material-symbols-outlined !text-sm ml-1">event_repeat</span>
                </Tooltip>
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4 shrink-0">
            <MeetingAttendees resolved={meeting.user_attendees} unresolved={meeting.unresolved_attendees} />
            <div className="min-w-[145px] max-w-[165px] w-[165px] flex justify-end">
              <CollectionPicker<MeetingResponse>
                meetingId={meeting.id}
                collection={meeting.collection}
                onMeetingUpdated={onMeetingUpdated}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
