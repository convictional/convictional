import { mountIsland } from "~/react/shared/mountIsland"
import { OrganizationUsers } from "./OrganizationUsers"

function mount() {
  // No props — identity comes from useCurrentUser().
  mountIsland("react-organization-users", () => <OrganizationUsers />)
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
