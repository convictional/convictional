import { mountIsland } from "~/react/shared/mountIsland"

import { MainNav, type MainNavProps } from "./MainNav"

function mount() {
  mountIsland<MainNavProps>("react-main-nav", props => (
    <MainNav
      isAdmin={props.isAdmin ?? false}
      isSuperuser={props.isSuperuser ?? false}
      organizationName={props.organizationName ?? null}
    />
  ))
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount)
} else {
  mount()
}

document.addEventListener("htmx:load", mount)
