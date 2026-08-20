import { mountIsland } from "~/react/shared/mountIsland"
import { MeetingsIndex } from "./MeetingsIndex"
import type { MeetingsIndexProps } from "./types"

function mount() {
  mountIsland<MeetingsIndexProps>("react-meetings-index", props => <MeetingsIndex {...props} />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
