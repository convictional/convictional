import { useState } from "react"

import { ResourceBadge } from "~/react/composites/ResourceBadge"
import { connectCalendarWithPreference } from "~/react/shared/recall_ai/calendarConnect"
import { EmptyStateSurface } from "~/react/ui/EmptyStateSurface"
import { GoogleCalendarLogo } from "~/react/ui/GoogleCalendarLogo"

interface CalendarConnectionPromptProps {
  googleCalendarLoginUrl: string
}

// The lifecycle of one meeting, told as a connected timeline so the three beats read as a single
// arc rather than a list of features: a shared agenda is the calendar-only prep benefit; the
// waiting-room admission is the "you're always in control" reassurance; the sectioned summary is
// the payoff. Section names mirror the real generated summary (Decisions / Key Points / Risks).
const LIFECYCLE: { icon: string; title: string; detail: string }[] = [
  {
    icon: "description",
    title: "A shared agenda, before",
    detail: "Everyone shapes one live agenda doc for each upcoming call, so it starts prepared.",
  },
  {
    icon: "meeting_room",
    title: "You're in control, during",
    detail:
      "The Notetaker waits to be admitted and can be denied on any call. It follows the substance and skips the small talk.",
  },
  {
    icon: "move_to_inbox",
    title: "A summary, after",
    detail: "Decisions, key points, and risks, written up in your inbox and searchable.",
  },
]

function Lifecycle() {
  return (
    <ol>
      {LIFECYCLE.map((step, i) => {
        const last = i === LIFECYCLE.length - 1
        return (
          <li key={step.title} className="flex gap-3.5">
            <div className="flex flex-col items-center">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-base-300 bg-base-100 text-base-content/70">
                <span className="material-symbols-outlined leading-none" style={{ fontSize: "18px" }}>
                  {step.icon}
                </span>
              </span>
              {/* Connector rail between this node and the next, so the beats read as one arc. */}
              {!last && <span className="my-1 w-px flex-1 bg-base-300" aria-hidden />}
            </div>
            <div className={last ? "" : "pb-5"}>
              <div className="text-sm font-medium text-base-content">{step.title}</div>
              <p className="mt-0.5 text-xs text-base-content/60 text-pretty">{step.detail}</p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

// The first-run surface for meetings: no calendar is connected yet, so nothing can be recorded.
export function CalendarConnectionPrompt({ googleCalendarLoginUrl }: CalendarConnectionPromptProps) {
  const [autoJoin, setAutoJoin] = useState(true)
  const connect = () => connectCalendarWithPreference(googleCalendarLoginUrl, autoJoin)

  return (
    <EmptyStateSurface className="overflow-hidden">
      <div className="flex flex-col gap-10 p-8 lg:flex-row lg:items-start lg:gap-14 lg:p-12">
        <div className="flex flex-col items-center text-center lg:w-1/2 lg:items-start lg:text-left">
          <div className="flex items-start gap-3.5 text-left">
            <div className="shrink-0 rounded-2xl border border-base-300 bg-base-50 p-1 shadow-sm">
              <ResourceBadge contentType="meeting" size="medium" />
            </div>
            <div className="max-w-md">
              <h2 className="font-accent text-lg text-base-content text-balance">Turn every meeting into knowledge</h2>
              <p className="mt-1.5 text-sm text-base-content/60 text-pretty">
                Connect your calendar and the Notetaker handles the rest, from prep before the call to a written record
                after.
              </p>
            </div>
          </div>

          <div className="mt-6 w-full max-w-sm rounded-xl border border-base-300 bg-base-50 p-3.5 text-left">
            <label className="flex cursor-pointer items-start justify-between gap-3">
              <span className="min-w-0">
                <span className="text-sm font-medium text-base-content">Auto-join meetings</span>
                <span className="mt-0.5 block text-xs text-base-content/60">
                  Records, transcribes, and summarizes calls. Private by default.
                </span>
              </span>
              <input
                type="checkbox"
                className="toggle toggle-primary toggle-sm mt-0.5 shrink-0"
                checked={autoJoin}
                onChange={event => setAutoJoin(event.target.checked)}
                aria-label="Auto-join meetings with the Notetaker"
              />
            </label>
            {/* Connect lives with the toggle: the toggle sets the preference this navigation carries. */}
            <button type="button" className="btn btn-primary mt-3.5 w-full gap-1.5" onClick={connect}>
              <span className="w-4">
                <GoogleCalendarLogo />
              </span>
              Connect Calendar
            </button>
          </div>
        </div>

        <div className="mx-auto w-full max-w-sm lg:mx-0 lg:w-1/2 lg:pt-1">
          <Lifecycle />
        </div>
      </div>
    </EmptyStateSurface>
  )
}
