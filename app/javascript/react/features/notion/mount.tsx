import { mountIsland } from "~/react/shared/mountIsland"
import { NotionSettings } from "./NotionSettings"

function mount() {
  mountIsland("react-notion-settings", () => <NotionSettings />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

// Re-mount after htmx boosted navigation swaps in new page content.
// mountIsland is idempotent — skips if already mounted.
document.addEventListener("htmx:load", mount)
