import type { MeetingResponse } from "~/react/shared/types"
import { DateTime } from "~/react/ui/DateTime"

interface UpcomingMeetingRowProps {
  meeting: MeetingResponse
  highlight: boolean
  timezone: string | null
}

// Times render in the user's configured tz (not browser-local) via DateTime.
export function UpcomingMeetingRow({ meeting, highlight, timezone }: UpcomingMeetingRowProps) {
  const completed = meeting.is_completed
  const highlightClass = highlight ? "text-primary" : ""
  const struckThrough = completed || meeting.is_declined
  const attendeeCount = meeting.user_attendees.length + meeting.unresolved_attendees.length

  const title = meeting.title || "Untitled meeting"

  return (
    <li className="relative group">
      {/* Stretched-link pattern: the boosted <a> is a transparent overlay covering
          the whole row rather than a wrapper of the content. htmx's hx-boost handler
          fires in the document capture phase from the click target upward, so nesting
          an interactive control inside the anchor let a "Join" click reach the boost
          handler before React's onClick could preventDefault — the row navigated
          anyway (PR 8998). Keeping the anchor a sibling of the content means a click
          on the Join button has no boosted <a> ancestor, so htmx never boosts it. The
          row stays boosted-navigable (required for the #8744 OOM fix) because clicks
          anywhere else on the row land on this overlay. */}
      <a href={meeting.source_url} aria-label={`Open ${title}`} className="absolute inset-0" />
      <div
        className={`flex items-start md:items-center gap-3 px-3 py-3 bg-base-50 group-hover:bg-base-200 transition-colors${
          completed ? " opacity-60" : ""
        }`}
      >
        <span className={`text-sm shrink-0 w-[60px] md:w-[150px] ${highlightClass}`}>
          {meeting.scheduled_at && (
            <>
              <DateTime datetime={meeting.scheduled_at} format="time" timezone={timezone} />
              {meeting.scheduled_end_at && (
                <>
                  <span className="hidden md:inline">–</span>
                  <DateTime datetime={meeting.scheduled_end_at} format="time" timezone={timezone} />
                </>
              )}
            </>
          )}
        </span>
        <div className="flex-1 min-w-0 flex flex-col gap-1 md:flex-row md:items-center md:gap-3">
          <span
            className={`text-sm font-semibold truncate md:flex-1 ${highlightClass}${
              struckThrough ? " line-through" : ""
            }`}
          >
            {title}
          </span>
          {meeting.is_happening_now && (
            <span className="badge badge-sm badge-primary self-start md:self-auto">Now</span>
          )}
          {meeting.conferencing_url && (
            // z-10 lifts it above the stretched-anchor overlay so its own clicks land
            // here. stopPropagation/preventDefault are defense in depth (see row comment).
            <button
              type="button"
              className={`relative z-10 btn btn-sm rounded-full cursor-pointer self-start md:self-auto ${
                meeting.is_happening_now ? "btn-primary" : "btn-neutral"
              }`}
              onClick={e => {
                e.preventDefault()
                e.stopPropagation()
                window.open(meeting.conferencing_url!, "_blank", "noopener,noreferrer")
              }}
            >
              Join
            </button>
          )}
          <div className="flex items-center gap-3 text-xs text-base-500 whitespace-nowrap md:ml-auto">
            <span>
              {attendeeCount} {attendeeCount === 1 ? "attendee" : "attendees"}
            </span>
            {/* `agenda` is blank for list rows, so the indicator reads the
                server-computed has_agenda flag. */}
            <span>{meeting.has_agenda ? "Agenda set" : "No agenda"}</span>
          </div>
        </div>
      </div>
    </li>
  )
}
