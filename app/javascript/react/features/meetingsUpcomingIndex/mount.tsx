import { mountIsland } from "~/react/shared/mountIsland"
import { MeetingsUpcomingIndex } from "./MeetingsUpcomingIndex"
import type { MeetingsUpcomingIndexProps } from "./types"

function mount() {
  mountIsland<MeetingsUpcomingIndexProps>("react-meetings-upcoming-index", props => (
    <MeetingsUpcomingIndex googleCalendarLoginUrl={props.googleCalendarLoginUrl} />
  ))
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
