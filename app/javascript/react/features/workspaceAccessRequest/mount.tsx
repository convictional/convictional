import { mountIsland } from "~/react/shared/mountIsland"
import type { WorkspaceAccessRequestProps } from "./types"
import { WorkspaceAccessRequest } from "./WorkspaceAccessRequest"

function mount() {
  mountIsland<WorkspaceAccessRequestProps>("react-workspace-access-request", props => (
    <WorkspaceAccessRequest {...props} />
  ))
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
