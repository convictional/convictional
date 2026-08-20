import { mountIsland } from "~/react/shared/mountIsland"

import { ResearchDialog } from "./ResearchDialog"

function mount() {
  mountIsland("react-research-dialog", () => <ResearchDialog />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
