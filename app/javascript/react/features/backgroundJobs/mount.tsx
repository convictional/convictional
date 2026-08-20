import { mountIsland } from "~/react/shared/mountIsland"
import { BackgroundJobs, type BackgroundJobsProps } from "./BackgroundJobs"

function mount() {
  mountIsland<BackgroundJobsProps>("react-background-jobs", props => <BackgroundJobs {...props} />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
