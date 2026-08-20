import { mountIsland } from "~/react/shared/mountIsland"
import { registerToastEventBridge } from "./eventBridge"
import { Toaster } from "./Toaster"

// Bridge the framework-agnostic showFlash() window event into the store, so
// vanilla callers (shared/csrf.ts) reach the <Toaster> without sharing a React
// tree. Registered once at module load (ES module singleton).
registerToastEventBridge()

function mount() {
  mountIsland("react-toaster", () => <Toaster />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
