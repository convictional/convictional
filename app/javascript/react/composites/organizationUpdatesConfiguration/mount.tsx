import { OrganizationUpdatesConfiguration } from "~/react/composites/organizationUpdatesConfiguration/OrganizationUpdatesConfiguration"
import { mountIsland } from "~/react/shared/mountIsland"

function mount() {
  mountIsland("react-organization-updates-configuration", () => <OrganizationUpdatesConfiguration />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
