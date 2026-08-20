import { mountIsland } from "~/react/shared/mountIsland"
import { ChatPanel } from "./ChatPanel"

function mount() {
  mountIsland("react-chat-panel", () => <ChatPanel />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

// Re-mount after htmx boosted navigation swaps in new page content.
// mountIsland is idempotent — skips if already mounted.
document.addEventListener("htmx:load", mount)
