import { mountIsland } from "~/react/shared/mountIsland"

import type { UserSettingsProps } from "./types"
import { UserSettings } from "./UserSettings"

function mount() {
  mountIsland<UserSettingsProps>("react-user-settings", props => <UserSettings {...props} />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

// Re-mount when navigation swaps in new page content; mountIsland is idempotent.
document.addEventListener("htmx:load", mount)
