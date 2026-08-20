import { mountIsland } from "~/react/shared/mountIsland"
import { FeedbackDialog, type FeedbackDialogProps } from "./FeedbackDialog"

function mount() {
  mountIsland<FeedbackDialogProps>("react-feedback-dialog", props => <FeedbackDialog {...props} />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
