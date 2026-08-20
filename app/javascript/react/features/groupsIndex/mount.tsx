import { mountIsland } from "~/react/shared/mountIsland"
import { GroupsIndex } from "./GroupsIndex"

function mount() {
  mountIsland<{ canManage?: boolean }>("react-groups-index", props => (
    <GroupsIndex canManage={props.canManage ?? false} />
  ))
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

// Re-mount after htmx boosted navigation swaps in new page content.
// mountIsland is idempotent — skips if already mounted.
document.addEventListener("htmx:load", mount)
