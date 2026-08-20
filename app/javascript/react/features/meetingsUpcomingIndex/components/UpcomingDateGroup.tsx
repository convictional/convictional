import dayjs from "dayjs"

import type { MeetingResponse } from "~/react/shared/types"
import { UpcomingMeetingRow } from "./UpcomingMeetingRow"

interface UpcomingDateGroupProps {
  dateKey: string
  todayKey: string
  tomorrowKey: string
  meetings: MeetingResponse[]
  concurrentNextMeetingIds: Set<string>
  timezone: string | null
}

export function UpcomingDateGroup({
  dateKey,
  todayKey,
  tomorrowKey,
  meetings,
  concurrentNextMeetingIds,
  timezone,
}: UpcomingDateGroupProps) {
  return (
    <div>
      <h3 className="text-sm font-semibold px-1 mb-2">
        <DateHeader dateKey={dateKey} todayKey={todayKey} tomorrowKey={tomorrowKey} />
      </h3>
      <ol className="divide-y divide-base-300 border border-base-300 rounded-2xl overflow-hidden shadow-xs">
        {meetings.map(meeting => (
          <UpcomingMeetingRow
            key={meeting.id}
            meeting={meeting}
            highlight={concurrentNextMeetingIds.has(meeting.id)}
            timezone={timezone}
          />
        ))}
      </ol>
    </div>
  )
}

function DateHeader({ dateKey, todayKey, tomorrowKey }: { dateKey: string; todayKey: string; tomorrowKey: string }) {
  if (dateKey === todayKey) return <>Today</>
  if (dateKey === tomorrowKey) return <>Tomorrow</>
  const day = dayjs(dateKey)
  return (
    <>
      {day.format("MMM D")}
      <span className="font-normal text-base-500 ml-1">{day.format("dddd")}</span>
    </>
  )
}
