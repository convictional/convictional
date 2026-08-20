import { mountIsland } from "~/react/shared/mountIsland"
import { MeetingShow } from "./MeetingShow"
import type { MeetingShowProps } from "./types"

function mount() {
  mountIsland<MeetingShowProps>("react-meeting-show", props => <MeetingShow {...props} />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
