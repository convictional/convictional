import { mountIsland } from "~/react/shared/mountIsland"
import { MeetingsCollectionsIndex } from "./MeetingsCollectionsIndex"

function mount() {
  mountIsland("react-meetings-collections-index", () => <MeetingsCollectionsIndex />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
