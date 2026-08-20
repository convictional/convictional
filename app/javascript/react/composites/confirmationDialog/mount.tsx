import { mountIsland } from "~/react/shared/mountIsland"
import { ConfirmationDialog } from "./ConfirmationDialog"

function mount() {
  mountIsland("react-confirmation-dialog", () => <ConfirmationDialog />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
