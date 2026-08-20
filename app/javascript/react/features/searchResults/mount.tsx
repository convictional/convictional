import { mountIsland } from "~/react/shared/mountIsland"
import { SearchResults } from "./SearchResults"

function mount() {
  mountIsland<{ initialQuery?: string }>("react-search-results", props => (
    <SearchResults initialQuery={props.initialQuery} />
  ))
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

// Re-mount when htmx:load fires after navigation swaps in new content.
// mountIsland is idempotent — skips if already mounted.
document.addEventListener("htmx:load", mount)
