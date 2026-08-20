import type { WorkspaceCollaboratorsProps } from "~/react/composites/workspaceCollaborators/types"
import { WorkspaceCollaborators } from "~/react/composites/workspaceCollaborators/WorkspaceCollaborators"
import { mountIsland } from "~/react/shared/mountIsland"

function mount() {
  mountIsland<WorkspaceCollaboratorsProps>("react-workspace-collaborators", props => (
    <WorkspaceCollaborators {...props} />
  ))
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
