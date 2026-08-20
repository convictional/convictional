import { mountIsland } from "~/react/shared/mountIsland"
import { CommandPalette } from "./CommandPalette"

function mount() {
  mountIsland("react-command-palette", () => <CommandPalette />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
