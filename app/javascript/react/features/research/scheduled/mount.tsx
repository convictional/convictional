import { mountIsland } from "~/react/shared/mountIsland"

import { ScheduledResearchIndex } from "./ScheduledResearchIndex"

function mount() {
  mountIsland("react-scheduled-research", () => <ScheduledResearchIndex />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

// Re-mount when navigation swaps in new page content; mountIsland is idempotent.
document.addEventListener("htmx:load", mount)
